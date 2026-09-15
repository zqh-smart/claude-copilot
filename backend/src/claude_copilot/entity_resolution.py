from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

_LEGAL_SUFFIXES = {
    "co",
    "company",
    "corp",
    "corporation",
    "inc",
    "incorporated",
    "limited",
    "llc",
    "llp",
    "ltd",
    "plc",
}
_CJK_LEGAL_SUFFIXES = (
    "集团股份有限公司",
    "股份有限公司",
    "有限责任公司",
    "集团有限公司",
    "股份公司",
    "有限公司",
)


@dataclass(frozen=True)
class ResolvedEntity:
    entity_id: str
    canonical_key: str
    canonical_name: str
    aliases: tuple[str, ...]


class EntityResolver:
    """Deterministic identity resolution shared by SQL and graph storage."""

    def resolve_company(
        self, name: str, *, aliases: tuple[str, ...] | list[str] = ()
    ) -> ResolvedEntity:
        names = self._deduplicate_names((name, *aliases))
        keys = [self.canonical_key(candidate) for candidate in names]
        key = max(
            enumerate(keys),
            key=lambda item: (
                not item[1].isdigit(),
                len(item[1]),
                item[0] == 0,
            ),
        )[1]
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]
        slug = re.sub(r"[^a-z0-9]+", "-", key).strip("-") or "company"
        return ResolvedEntity(
            entity_id=f"{slug[:40]}-{digest}",
            canonical_key=key,
            canonical_name=names[0],
            aliases=tuple(names),
        )

    def canonical_key(self, name: str) -> str:
        normalized = unicodedata.normalize("NFKC", name).casefold()
        normalized = re.sub(r"\([^)]{1,100}\)", " ", normalized).replace("&", " and ")
        compact = re.sub(r"\s+", "", normalized)
        for suffix in _CJK_LEGAL_SUFFIXES:
            if compact.endswith(suffix) and len(compact) > len(suffix):
                compact = compact[: -len(suffix)]
                normalized = compact
                break
        tokens = re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", normalized)
        while tokens and tokens[-1] in _LEGAL_SUFFIXES:
            tokens.pop()
        if tokens and tokens[-1] == "and":
            tokens.pop()
        return "".join(tokens) or "company"

    def stable_entity_id(self, prefix: str, name: str, *, owner_id: str | None = None) -> str:
        normalized = unicodedata.normalize("NFKC", name).casefold()
        key = "".join(re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", normalized))
        payload = "\x1f".join(part for part in (owner_id, key or "entity") if part)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return f"{prefix}:{digest}"

    @staticmethod
    def _deduplicate_names(names: tuple[str, ...]) -> list[str]:
        result, seen = [], set()
        for name in names:
            cleaned = re.sub(r"\s+", " ", name).strip(" \t\r\n,;:-")
            fingerprint = unicodedata.normalize("NFKC", cleaned).casefold()
            if cleaned and fingerprint not in seen:
                seen.add(fingerprint)
                result.append(cleaned)
        return result


def build_canonical_company_id(company_name: str) -> str:
    return EntityResolver().resolve_company(company_name).entity_id
