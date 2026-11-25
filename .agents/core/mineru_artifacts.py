"""Recognize archived MinerU artifact names across supported parser exports."""


def mineru_artifact_name(name: str) -> str | None:
    for kind, aliases in (
        ("middle_json.json", ("_middle.json", "_middle_json.json")),
        ("content_list.json", ("_content_list.json",)),
        ("content_list_v2.json", ("_content_list_v2.json",)),
        ("model_output.json", ()),
        ("structured_content.json", ()),
    ):
        if name == kind or name.endswith(aliases):
            return kind
    return "middle_json.json" if name == "middle.json" else None
