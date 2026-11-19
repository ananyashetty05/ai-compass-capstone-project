from app.services import model_classifier as mc, pool_stats


def c(name, ids=None, in_m=("text",), out_m=("text",), caps=(), sources=("huggingface",), ow=True, **kw):
    return mc.classify(name=name, offering_ids=ids or [name], in_m=in_m, out_m=out_m, caps=caps, sources=sources, open_weights=ow, **kw)


def test_modalities_decide_specialised_types():
    assert c("bge-m3", out_m=("embeddings",)).kind == "embedding"
    assert c("x-reranker-large").kind == "reranker"
    assert c("sdxl", out_m=("image",)).kind == "image_generation"
    assert c("clip-gen", out_m=("video",)).kind == "video_generation"
    assert c("whisper-base", in_m=("audio",)).kind == "speech"
    assert c("deepseek-coder-33b-instruct").primary_category == "developer"      # coding-specialised beats instruct
    assert c("Foo-Base").kind == "base_model" and c("Foo-Base").primary_category == "developer"


def test_chat_evidence_and_provider_name_is_never_evidence():
    assert c("x/model", sources=("openrouter",), ow=None).primary_category == "conversational"
    assert c("Llama-3-8B-Instruct").primary_category == "conversational"
    assert c("Gemma-3-4b-it", in_m=("text", "image")).kind == "multimodal_chat"
    assert c("Mystery", out_m=()).primary_category == "unclassified"          # no declared output: stays visible as unclassified


def test_applications_are_their_own_primary_category():
    k = c("ChatGPT", entry_type="application_integration")
    assert k.primary_category == "application" and k.kind == "consumer_app"


def test_curated_taxonomy_wins_and_overlapping_audience_tags():
    k = c("Jamba", sources=("curated_snapshot",), curated_type="chat", curated_categories=["conversational", "developer"])
    assert (k.primary_category, k.basis, k.use_categories) == ("conversational", "curated", ["conversational", "developer"])
    e = c("emb", sources=("curated_snapshot",), curated_type="embedding", curated_categories=["developer"])
    assert e.primary_category == "developer" and e.use_categories == ["developer"]


def _row(cat, key, kind="chat", tags=(), offers=1, entry="inference_model", active=True):
    return {"primary_category": cat, "category_kind": kind, "classification_basis": "derived", "capability_tags": list(tags), "entry_type": entry,
            "canonical_key": key, "model_id": key, "provider": "p", "active": active, "catalog": {"offerings": [{"provider": f"prov{i}"} for i in range(offers)]}}


def test_pool_stats_reconcile_and_separate_populations():
    rows = [_row("conversational", "a", tags=("chat", "coding"), offers=3), _row("developer", "b", "embedding"), _row("unclassified", "c", "unclassified"),
            _row("application", "app/x", "consumer_app", entry="application_integration")]
    s = pool_stats.compute(rows, {"awaiting_verification": 7, "retired": 2})
    assert s["pool_total"] == 4 and sum(s["primary"].values()) == 4
    assert s["canonical_models"] == 3 and s["applications"] == 1
    assert s["provider_offerings"]["count"] == 6                              # offerings are a separate population
    assert s["capabilities"]["overlapping"] is True
    assert (s["pending_verification"], s["retired"]) == (7, 2) and s["integrity"]["ok"] is True


def test_integrity_audit_flags_duplicates_and_inactive_rows():
    s = pool_stats.compute([_row("developer", "dup"), _row("developer", "dup"), _row("developer", "z", active=False)])
    failed = {x["check"] for x in s["integrity"]["checks"] if not x["ok"]}
    assert {"no_duplicate_canonical_identities", "retired_or_inactive_excluded_from_active_pool"} <= failed and s["integrity"]["ok"] is False
    bad = pool_stats.compute([_row("weird", "q")])
    assert bad["integrity"]["problems"] and bad["primary"]["unclassified"] == 1  # invalid category is reported, not hidden


def test_registry_entries_are_all_classified_once():
    from app.services import registry_service
    entries = registry_service.build_registry(include_live=False)
    s = pool_stats.compute(entries)
    assert sum(s["primary"].values()) == len(entries) == s["pool_total"] and s["integrity"]["ok"]
