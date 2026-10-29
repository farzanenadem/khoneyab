def create_embedding(name: str, **kwargs):
    # Backends are imported lazily so that using one does not require the others.
    if name == "HuggingFace":
        from langchain_huggingface import HuggingFaceEmbeddings

        return HuggingFaceEmbeddings(
            model_name=kwargs["model"],
            model_kwargs={
                "device": kwargs.get("device", "cpu"),
                "trust_remote_code": True,
                "tokenizer_kwargs": {
                    "fix_mistral_regex": True,
                    "extra_special_tokens": {},
                },
                "config_kwargs": {"use_fast": False},
            },
            encode_kwargs={
                "normalize_embeddings": True,
                "truncate_dim": kwargs.get("truncate_dim", 768),  # [1024 / 768]
                "batch_size": kwargs.get("batch_size", 32),
            },
        )
    if name == "ollama":
        from langchain_ollama import OllamaEmbeddings

        return OllamaEmbeddings(
            model=kwargs["model"],
            base_url=kwargs.get("url"),
        )
    raise ValueError("Invalid embedding name.")
