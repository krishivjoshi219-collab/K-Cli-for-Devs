# Security policy

## Reporting a vulnerability

Please do not open public issues for vulnerabilities or exposed credentials. Contact the maintainer privately through GitHub and include reproduction steps, impact, and any suggested mitigation.

## Secrets

K-CLI reads provider credentials from environment variables. Never commit `.env`, model tokens, generated datasets, or notebooks containing credentials. If a token reaches a repository, revoke it at the provider immediately and remove it from the repository history before publishing.

## Execution boundary

K-CLI's verifier executes generated code and supplied tests as local subprocesses. It strips common credential variables, starts a separate process group, applies conservative POSIX CPU/file/descriptor limits where available, and kills the full child group on timeout. These controls are defense-in-depth, not a security sandbox: subprocesses still retain the caller's filesystem permissions and network access. Treat repositories and model output as untrusted input and use a disposable container or virtual machine for hostile code.

Model downloads must be verified against a trusted SHA-256 reference before installation. If a trusted digest is unavailable, K-CLI fails closed rather than treating the computed digest as proof of authenticity.
