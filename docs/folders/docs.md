# Folder Reference: docs

## Purpose

Project documentation set for users, operators, and contributors.

## Contents

- system docs (`architecture`, `installation`, `configuration`, `usage`, `testing`, `deployment`)
- operational docs (`admin-tooling`, `mcp_guide`)
- process docs (`developer-guidelines`, `roadmap`)
- module/folder references (`docs/folders/*.md`)

## Publishing

Site build configuration is in `mkdocs.yml`, and deployment runs in `.github/workflows/ci.yml`.

## Validation

```bash
mkdocs build --strict
```
