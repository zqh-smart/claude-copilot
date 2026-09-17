from app.pipeline.feature_pipeline.chunking.contextual import apply_contextual_prefix


def test_apply_contextual_prefix_prepends_header() -> None:
    prefix = "公司：测试\n正文："
    body = "营业收入同比增长 10%。"
    merged = apply_contextual_prefix(body, prefix)
    assert merged.startswith("公司：测试")
    assert "营业收入" in merged
