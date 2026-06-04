import pulumi
import pulumi_aws as aws

# Simple test resource
bucket = aws.s3.Bucket(
    "test-bucket",
    bucket="test-bucket-affinity-12345",
)

pulumi.export("bucket_name", bucket.id)
