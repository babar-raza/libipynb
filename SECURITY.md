# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Pre-release, actively maintained |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly by emailing
the maintainer directly rather than opening a public issue.

## Security Features

libipynb includes built-in protections against common notebook-related security risks:

- **Resource limits** — configurable caps on input size, nesting depth, and entry count
- **Content sanitization** — detection and handling of active content in outputs
- **Path safety** — prevention of path traversal in export and attachment operations
- **Trust levels** — configurable trust policies for notebook content
