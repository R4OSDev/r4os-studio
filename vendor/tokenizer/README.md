# Pinned local tokenizer

OpenAI tiktoken 0.14.0 (MIT) and two official BPE tables, provisioned offline with Studio.

The wheel targets CPython 3.13, Linux x86_64 and glibc >=2.28. Other hosts use the explicit character fallback.
`manifest.json` pins package files, table hashes, upstream model mappings and provenance.
No runtime download, pip install or model process is used. The wrapper constructs Encoding from local verified tables.
Only explicit upstream model mappings on qualified OpenAI connections are used; unknown models retain the character fallback.

License: LICENSE. Original wheel SHA-256: 26e60f6a956ee171ab728b37b8439905d7ea1db435c30f9822f291e9861c861d
