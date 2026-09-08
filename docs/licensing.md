# Licensing

OpenCCForSigil's project-authored source code and documentation are released
under the **Apache License, Version 2.0**. The complete license text is in the
repository [`LICENSE`](../LICENSE); the canonical text is also published by
the [Apache Software Foundation](https://www.apache.org/licenses/LICENSE-2.0).
It is included at the root of the
installable plugin package as `OpenCCForSigil/LICENSE`.

Apache-2.0 is a permissive license suitable for a cross-platform Sigil plugin:
it allows use, modification, redistribution, and commercial distribution,
while providing an explicit patent grant. It also aligns with the license of
the vendored official OpenCC Python Binding.

The project license does not replace third-party licenses. The release package
preserves the official OpenCC Apache-2.0 license and authors notice inside
each vendored wheel payload. The optional official native Jieba payload uses
the upstream `cppjieba` dependency, whose MIT notice is retained at
`OpenCCForSigil/resources/third_party/CPPJIEBA_LICENSE`. See
[`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) for the provenance
summary.

When redistributing the plugin, provide a copy of the canonical `LICENSE`, keep
`NOTICE`, and retain the applicable copyright, patent, trademark, and
attribution notices from the project and bundled components. If you modify
files, add a prominent notice stating that you changed the files, as required
by Apache-2.0 section 4(b). Do not describe OpenCCForSigil as relicensing OpenCC
or cppjieba; each component remains under its original terms.

The Apache-2.0 patent grant in section 3 covers only patent claims that a
contributor can license and that are necessarily infringed by that
contributor's contribution. This project license does not replace the separate
licenses or patent terms of bundled components: OpenCC has its own Apache-2.0
terms, while cppjieba retains its MIT terms. The project grant does not grant
trademark rights, and it terminates for a party that files patent litigation
alleging that the work or a contribution infringes a patent. Consult the
canonical `LICENSE` for the complete terms.
