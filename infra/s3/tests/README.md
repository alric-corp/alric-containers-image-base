The native AWS mock tests live in `../../ecr/tests/s3.tftest.hcl`, alongside
the existing catalog tests. They select this child with `source = "../s3"`.
Terraform requires the test directory to be local to the execution root.
Run `terraform -chdir=infra/ecr test`; do not initialize this child separately.
Python plan, state-boundary and AWS-response probes live in `../../tests/`.
