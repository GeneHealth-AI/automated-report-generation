import rag  # pyright: ignore[reportImplicitRelativeImport]

pm = rag.PubMedRAG(email="sskolusa@gmail.com",api_key="cc4c8e3a576269291de09db7fb095ea8b008")


print(pm.get_evidence_context("breast cancer"))