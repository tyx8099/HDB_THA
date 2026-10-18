# Part 2: AWS data platform architecture

This section proposes a small production architecture for collecting the HDB
resale dataset from data.gov.sg, cleaning it, and making the curated data
available to Tableau. One diagram shows the complete flow.

## Design assumptions

- The platform runs in one AWS Region and one AWS account.
- data.gov.sg is a public website. Lambda needs controlled internet access to
  download the files, but it does not accept connections from the internet.
- Input files may exceed 100 MB. The downloader streams each response to S3
  rather than holding the whole file in memory.
- Each download is assumed to finish within Lambda's 15-minute limit. Lambda
  keeps only a small part of the file in memory while it uploads the file to
  S3. CloudWatch alerts the team if downloads run too long or fail.
- Daily ingestion is sufficient for this batch dataset. The EventBridge
  schedule can be changed without changing the pipeline.
- Tableau users see only approved published data sources and workbooks backed
  by Athena views. They do not receive AWS credentials. Raw and quarantine
  data remain restricted to the engineering role.
- Curated data is stored as compressed Parquet files and partitioned by
  transaction year. Month remains a normal column. Year-only partitioning is
  sufficient for this dataset and avoids creating many small monthly files.

### Large-file processing boundary

Lambda uploads the file to S3 in parts as it downloads it, so the complete file
is never held in memory. AWS Glue performs the more complex data processing.
The download must finish within Lambda's 15-minute limit.

## 1. Batch ingestion plan

### Flow

1. Amazon EventBridge starts the pipeline each day. AWS Step Functions then
   runs the steps in order and handles retries.
2. Step Functions starts a Lambda function in private subnets. Lambda reaches
   data.gov.sg through AWS Network Firewall and a NAT Gateway. The firewall
   allows HTTPS access to `.data.gov.sg`, which is AWS notation for the domain
   and its subdomains. If a download redirects to another host, that host must
   be checked and added to the allowlist. Network rules allow only the HTTPS
   traffic and its return traffic.
3. The function streams files larger than 100 MB using S3 multipart upload. It
   checks `Content-Length` when available, calculates SHA-256 while streaming,
   and records the size, SHA-256 fingerprint, dataset version, source URL, and
   run ID in object metadata and a run manifest. The fingerprint helps with
   auditing and detecting changed files. It can only prove that a file matches
   the source if the publisher provides a trusted checksum to compare against.
4. An S3 Gateway Endpoint gives Lambda a private route to S3, so uploads do not
   pass through the NAT Gateway.
5. Step Functions starts an AWS Glue job. The job validates the schema and
   quality rules, writes rejected rows to quarantine, and writes accepted data
   as Parquet partitioned by transaction year under a new folder for that run.
6. After checking the completed output, Glue updates the Data Catalog so Athena
   reads from the new folder. The previous folder is kept for a short period in
   case a rollback is needed, then removed by an S3 lifecycle rule. Step
   Functions records the result and sends an SNS alert if the run fails.

The data.gov.sg API key is stored in Secrets Manager. If the API returns HTTP
429 because too many requests were made, the downloader waits longer after
each attempt, adds a small random delay, and stops after a fixed number of
retries.

### Private service paths

- Lambda reaches CloudWatch Logs, Secrets Manager, and KMS through private VPC
  endpoints. It uses the NAT Gateway only for the approved data.gov.sg request.
- The AWS Glue job is configured to access resources inside the VPC. When the
  job starts, Glue creates temporary network interfaces with private IP
  addresses in the data subnets. These interfaces use the S3 Gateway Endpoint
  and private endpoints for Secrets Manager, KMS, CloudWatch Logs, and Glue.
- The endpoint security groups accept HTTPS only from the Lambda and Glue
  security groups. Endpoint policies limit access to the required AWS roles,
  actions, secrets, keys, buckets, and folders.

### Operational controls

| Area | Design choice |
| --- | --- |
| Security | Lambda and Glue have no public IP address and accept no incoming internet traffic. Network Firewall limits outgoing internet traffic to data.gov.sg. Each service has an IAM role that grants only the access it needs. S3 public access is blocked. |
| Reliability | Step Functions retries failed steps a limited number of times and sends final failures to SNS. The pipeline writes raw files with unique versioned keys and does not overwrite them. S3 versioning preserves earlier object versions. Public, inspection, and private subnets span multiple Availability Zones, with one NAT Gateway and Network Firewall endpoint per Availability Zone. The diagram uses one icon to represent each repeated resource. |
| Data quality | The job validates the expected schema, authoritative values, duplicates, nulls, lease calculations, and price anomaly flags. Invalid records go to quarantine with their reasons. |
| Integrity | The downloader checks the expected file size when it is available and records a SHA-256 fingerprint for auditing and change detection. It stops multipart uploads when it handles a failure. An S3 lifecycle rule removes unfinished uploads left by a timeout or unexpected termination. |
| Repeat runs | Raw file names include the source version and extraction date. Glue writes each run to a new folder, checks the output, and then points the affected year partitions in the Data Catalog to that folder. Repeating a run does not add duplicate rows to the active data. |
| Scalability | Lambda does not keep the complete file in memory. Glue can add more workers for larger transformations, and S3 grows without storage servers to manage. |
| Performance | Parquet compression reduces storage and scanning. Year partitions let Athena skip unrelated years without creating many small monthly files. The S3 Gateway Endpoint keeps S3 traffic off the NAT Gateway. |
| Maintainability | Step Functions keeps the download, validation, transformation, catalog update, and notification steps separate. CloudWatch keeps their logs, metrics, alerts, and run identifiers in one place. |
| Cost | Services are serverless or run only for each batch. Lifecycle rules abort incomplete multipart uploads, move old raw and superseded curated versions to cheaper storage, and expire temporary Athena results. |

## 2. Tableau exploitation plan

### Flow

1. Corporate users connect through a Site-to-Site VPN and an internal
   Application Load Balancer. HTTPS encrypts traffic to Tableau.
   Tableau uses the corporate identity provider for single sign-on and
   multi-factor authentication (MFA).
2. Tableau Server runs in private subnets across multiple Availability Zones
   for availability.
3. Tableau connects to Athena with its JDBC or ODBC driver. An Athena Interface
   VPC Endpoint keeps this connection on the AWS network.
4. Athena reads the approved view definitions from the Glue Data Catalog and
   scans the curated data in S3 using Tableau's query role. Tableau Server keeps
   this AWS role. Individual Tableau users do not receive its credentials.
5. Athena stores encrypted query results in a dedicated S3 folder, called a
   prefix in S3. Tableau receives the rows through the Athena JDBC or ODBC
   driver.

Athena and S3 are AWS managed services in the same Region. The Tableau and
ingestion VPCs therefore do not need a direct network connection to each other.

### Access and query controls

- Tableau project permissions control which users can open each published data
  source, workbook, and dashboard. Those published data sources query approved
  Athena views.
- Standard Athena views organise the data exposed through Tableau, but they are
  not an S3 security boundary. The Tableau query role still needs read access
  to the underlying curated files. End users cannot bypass the views because
  they receive neither this role nor direct Athena access.
- The Tableau query role has `s3:PutObject` and `s3:GetObject` on its dedicated
  Athena results prefix, plus limited `s3:ListBucket` and
  `s3:GetBucketLocation` permissions required for that location. It also has
  read access to the curated folder because Athena views require access to
  their underlying S3 data.
- The role can run queries only in the dedicated Tableau workgroup. Only
  Tableau Server assumes this role. Tableau users have no Athena console or API
  access.
- The Athena workgroup fixes the results location, requires KMS encryption,
  records query metrics, and limits how much data one query can scan.
- The Athena endpoint policy allows only the Tableau query role and its
  required actions. The ingestion S3 Gateway Endpoint policy allows only the
  named buckets, folders, roles, and actions used by Lambda and Glue.
- S3 bucket policies apply `aws:SourceVpce` or `aws:SourceVpc` conditions to
  requests made through approved VPC endpoints or the VPC. Athena is an AWS
  managed service, so the policies also allow its named query role and service
  requests through `aws:ViaAWSService`. Without this exception, a rule that
  allows only VPC endpoints would block Athena.
- KMS key policies allow only the required service roles to encrypt or decrypt
  data. TLS encrypts network connections.
- CloudTrail records changes to AWS resources and permissions. CloudWatch
  collects Athena and Tableau metrics and sends alerts.
- Tableau extracts can be scheduled for repeated dashboards. Interactive
  queries remain available when current data is required.

## Main trade-offs

- **Lambda instead of Fargate:** Lambda needs less setup and has no container
  image to maintain. It uploads files over 100 MB to S3 in parts. Each download
  must still finish within 15 minutes and stay within the configured memory and
  temporary storage limits. The downloader can move to Fargate if monitoring
  shows that these limits are becoming a problem.
- **Glue instead of a permanent Spark cluster:** Glue suits periodic batch
  transformation and avoids maintaining always-on compute.
- **Athena instead of another database:** Athena queries the files in S3, so
  there is no database server to run. Frequently used dashboards can use
  Tableau extracts for faster loading and fewer Athena scans.
- **Private endpoint instead of connecting the VPCs:** Tableau needs private
  access to Athena rather than direct access to the ingestion VPC. The Athena
  Interface Endpoint provides this with less network routing to manage.
- **Site-to-Site VPN instead of Direct Connect:** The VPN is quicker and cheaper
  to set up. Direct Connect is an option if the organisation later needs more
  predictable bandwidth and latency.
- **IAM and Tableau permissions instead of Lake Formation:** A dedicated query
  role, Athena views, and Tableau project permissions are enough for this public
  dataset. Lake Formation can be added if future datasets need AWS-enforced
  table, column, or row access rules.
- **Year partitions instead of year and month:** Year-only partitioning lets
  Athena skip unrelated years while avoiding many small monthly files and
  catalog entries.
- **Versioned folders instead of overwriting curated files:** Glue writes each
  run to a new folder, validates it, and then points the Data Catalog at the new
  data. This uses more storage temporarily but prevents incomplete output from
  becoming active and supports rollback.
- **Multi-AZ instead of single-AZ:** Multiple Availability Zones reduce the
  effect of a zone failure. The trade-off is higher infrastructure cost and a
  more involved Tableau deployment.
- **Network Firewall instead of unrestricted NAT access:** The firewall limits
  Lambda's internet access to approved download domains. It adds cost and
  network configuration compared with NAT access alone.
- **EventBridge Scheduler with Step Functions instead of scheduling Lambda
  directly:** The separate workflow provides visible steps, retries, and
  failure handling across Lambda and Glue. Directly scheduling Lambda would use
  fewer services but would move that orchestration into application code.
- **Primary-region resilience without a formal disaster recovery target:** S3
  versioning and Multi-AZ resources handle common failures. A regional recovery
  target would also require replicated infrastructure, metadata, permissions,
  Tableau recovery, and a tested failover process.
