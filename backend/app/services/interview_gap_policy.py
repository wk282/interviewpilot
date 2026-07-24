from collections.abc import Iterable


NON_TECHNICAL_GAP_MARKERS = (
    "术语使用",
    "表述",
    "措辞",
    "用词",
    "语法",
    "错别字",
    "语言组织",
    "判卷",
    "判级",
    "terminology",
    "wording",
    "phrasing",
    "grammar",
    "typo",
)

GENERIC_FEEDBACK = {
    "回答缺少足够的技术细节",
    "需要补充实现过程和结果证据",
}


def filter_technical_gaps(
    values: Iterable[object] | None,
    limit: int = 6,
) -> list[str]:
    result: list[str] = []
    for value in values or []:
        normalized = " ".join(str(value).split()).strip()
        lowered = normalized.lower()
        if not normalized or normalized in GENERIC_FEEDBACK:
            continue
        if any(marker in lowered for marker in NON_TECHNICAL_GAP_MARKERS):
            continue
        if normalized not in result:
            result.append(normalized[:200])
        if len(result) >= limit:
            break
    return result
