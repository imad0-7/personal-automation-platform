"""Conservative deterministic extraction; evidence and ambiguity are first-class data."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from automation_platform.core.config import load_yaml
from automation_platform.core.models import Listing


def _normalise(text: str) -> str:
    value = unicodedata.normalize('NFKC', text).upper().replace('×', 'X').replace('*', 'X')
    value = re.sub(r'(?<=\d)\s*[.-]\s*(?=\d)', '', value)
    value = re.sub(r'\bGE\s*FORCE\b', 'GEFORCE', value)
    value = re.sub(r'\bM[.]?2\b', 'M2', value)
    value = re.sub(r'\s+', ' ', value)
    return value.strip()


def _compact(value: str) -> str:
    return re.sub(r'[^A-Z0-9]', '', value.upper())


def _confidence(kind: str) -> float:
    return {'explicit': 1.0, 'reference': 0.98, 'inferred': 0.9,
            'probable': 0.78, 'fuzzy': 0.72, 'user': 1.0,
            'conflict': 0.0}.get(kind, 0.5)


def extract(text: str) -> dict:
    raw = _normalise(text)
    reference = load_yaml(Path(__file__).with_name('hardware.yaml'))
    result: dict = {'raw': text, 'fields': {}, 'questions': []}
    fields = result['fields']

    def put(key, value, evidence, kind='explicit', confidence=None):
        confidence = _confidence(kind) if confidence is None else confidence
        if key in fields and fields[key]['value'] != value:
            fields[key] = {'value': None, 'evidence': 'Contradiction', 'kind': 'conflict',
                           'confidence': 0.0}
            question = f'{key} contradictoire'
            if question not in result['questions']:
                result['questions'].append(question)
        else:
            fields[key] = {'value': value, 'evidence': evidence, 'kind': kind,
                           'confidence': round(float(confidence), 2)}

    # Exact/reference CPU matching first. Normalization covers common separators.
    models = [(str(m), p) for p, ms in reference['platforms'].items() for m in ms]
    for model, platform in sorted(models, key=lambda x: -len(x[0])):
        pattern = r'(?<![A-Z0-9])' + re.escape(model) + r'(?![A-Z0-9])'
        # A Ryzen/CPU prefix or a suffixed model in a glued string is also supported.
        prefix = r'(?:RYZEN\s*[3579]?\s*|CPU\s*)' + re.escape(model)
        glued = re.escape(model) + r'(?=\d\s*X\s*\d)' if not model[-1].isdigit() else r'(?!)'
        model_match = re.search(pattern, raw)
        prefix_match = re.search(prefix + r'(?![A-Z])', raw)
        if model_match or prefix_match or re.search(glued, raw):
            # Bare numeric references near GPU/SSD labels are ambiguous, not Ryzen proof.
            if model.isdigit() and not re.search(prefix + r'(?![A-Z0-9])', raw):
                continue
            tier = re.search(r'RYZEN\s*([3579])\s*' + re.escape(model), raw)
            cpu_name = f"Ryzen {tier[1]} {model}" if tier else f'Ryzen {model}'
            put('cpu', cpu_name, model, 'reference')
            put('platform', platform, f'CPU {model}', 'inferred')
    for match in re.finditer(r'(?<![A-Z0-9])I[3579][ -]?\d{4,5}[A-Z]{0,2}(?![A-Z])', raw):
        intel = re.sub(r'\s+', ' ', match.group().replace('-', ' '))
        put('cpu', intel, match.group())

    # Conservative fuzzy CPU fallback for malformed Ryzen references.
    if 'cpu' not in fields:
        tokens = re.findall(r'[A-Z0-9]{4,12}', _compact(raw))
        for token in tokens:
            best = None
            for model, platform_name in models:
                score = SequenceMatcher(None, token, _compact(model)).ratio()
                if score >= 0.86 and (best is None or score > best[0]):
                    best = (score, model, platform_name)
            if best and re.search(r'RYZEN|AMD|CPU|R[3579]', raw):
                score, model, platform_name = best
                put('cpu', f'Ryzen {model}', token, 'fuzzy', min(0.85, score))
                put('platform', platform_name, f'CPU {model}', 'inferred')
                break
    for m in re.finditer(r'DDR\s*([345])', raw):
        put('ram_type', 'DDR' + m[1], m[0])
    platform = fields.get('platform', {}).get('value')
    if platform:
        put('ram_type', 'DDR5' if platform == 'AM5' else 'DDR4', platform, 'inferred')
    gpu_aliases = []
    for canonical, aliases in reference.get('gpus', {}).items():
        for alias in [canonical, *(aliases or [])]:
            gpu_aliases.append((canonical, _compact(str(alias))))
    compact_raw = _compact(raw)
    for canonical, alias in sorted(gpu_aliases, key=lambda x: -len(x[1])):
        if alias and alias in compact_raw:
            put('gpu', canonical, alias, 'reference')
            break
    if 'gpu' not in fields:
        for m in re.finditer(r'(RTX|GTX|RX)\s*(\d{3,4})(?:\s*(TI|XT|XTX))?(?:\s*(SUPER))?', raw):
            put('gpu', ' '.join(x for x in m.groups() if x), m[0])
    if 'gpu' not in fields and re.search(r'RTX|GTX|RADEON|\bRX\b|GEFORCE', raw):
        candidates = re.findall(r'(?:RTX|GTX|RX|RADEON|GEFORCE)[A-Z0-9 ]{3,16}', raw)
        for candidate in candidates:
            cc = _compact(candidate)
            best = None
            for canonical, alias in gpu_aliases:
                score = SequenceMatcher(None, cc, alias).ratio()
                if score >= 0.88 and (best is None or score > best[0]):
                    best = (score, canonical)
            if best:
                put('gpu', best[1], candidate, 'fuzzy', min(0.84, best[0]))
                break
    if 'gpu' not in fields:
        result['questions'].append('Carte graphique non identifiée')
    for m in re.finditer(r'([1248])\s*X\s*(\d{1,3})\s*(?:GO|GB|G)(?![A-Z])', raw):
        total = int(m[1]) * int(m[2])
        if total in {8, 16, 24, 32, 48, 64, 96, 128, 192, 256}:
            put('ram_gb', total, m[0], 'probable')
    if platform and 'ram_gb' not in fields:
        for m in re.finditer(r'(?<!\d)([1248])\s*X\s*(\d{1,3})(?!\d)', raw):
            if int(m[2]) in {4, 8, 16, 24, 32, 48, 64}:
                put('ram_gb', int(m[1]) * int(m[2]), m[0], 'probable')
    for m in re.finditer(r'(?:RAM|MEMOIRE|MEMORY)\s*[:=-]?\s*(\d{1,3})\s*(?:GO|GB|G)\b', raw):
        put('ram_gb', int(m[1]), m[0])
    if 'ram_gb' not in fields:
        for m in re.finditer(r'(?<!\d)(8|16|24|32|48|64|96|128)\s*(?:GO|GB)\s*(?:DDR[345])', raw):
            put('ram_gb', int(m[1]), m[0], 'probable', 0.86)
    # Avoid confusing GPU VRAM with system RAM: values adjacent to RTX/GTX/RX are ignored.
    if 'ram_gb' not in fields:
        for m in re.finditer(r'(?<!\d)(8|16|24|32|48|64)\s*(?:GO|GB)\b', raw):
            context = raw[max(0, m.start()-18):min(len(raw), m.end()+18)]
            if not re.search(r'RTX|GTX|RADEON|\bRX\b|VRAM', context):
                put('ram_gb', int(m[1]), m[0], 'probable', 0.68)
                break
    storage = []
    seen_storage = set()
    for m in re.finditer(r'(SSD|NVME|HDD|M2)\s*[:=-]?\s*(\d+(?:[.,]\d+)?)\s*(TO|TB|GO|GB)', raw):
        storage_type = 'NVME' if m[1] == 'M2' else m[1]
        key = (storage_type, m[2], m[3])
        if key not in seen_storage:
            storage.append({'type': storage_type, 'capacity': m[2] + ' ' + m[3],
                            'evidence': m[0], 'confidence': 1.0})
            seen_storage.add(key)
    if storage:
        fields['storage'] = {'value': storage, 'kind': 'explicit', 'evidence': str(storage),
                             'confidence': 1.0}
    else:
        capacities = re.findall(r'(?<!\d)(\d+(?:[.,]\d+)?)\s*(?:TO|TB|T)(?![A-Z])', raw)
        if capacities:
            fields['storage'] = {
                'value': [{'type': 'inconnu', 'capacity': x + ' To', 'confidence': 0.65}
                          for x in capacities],
                'kind': 'probable', 'evidence': 'Capacité seule, SSD/HDD inconnu',
                'confidence': 0.65,
            }
    if 'cpu' not in fields:
        result['questions'].append('Processeur non identifié')
    if fields.get('ram_gb', {}).get('kind') == 'probable' and fields['ram_gb'].get('confidence', 0) < 0.8:
        result['questions'].append('Confirmer la capacité de RAM')
    for key in ('cpu', 'gpu', 'ram_gb', 'storage'):
        if key in fields and fields[key].get('confidence', 1) < 0.75:
            question = f'Confirmer {key}'
            if question not in result['questions']:
                result['questions'].append(question)
    return result


def analyze_listing(listing: Listing, correction: dict | None = None) -> list[str]:
    text = ' '.join([listing.title, str(listing.attributes.get('description', '')),
                     str(listing.attributes.get('features', {}))])
    parsed = extract(text)
    for key, value in (correction or {}).items():
        parsed['fields'][key] = {'value': value, 'kind': 'user',
                                 'evidence': 'Correction personnelle', 'confidence': 1.0}
    if correction:
        parsed['questions'] = []
    listing.attributes['hardware'] = parsed
    fields = {k: v['value'] for k, v in parsed['fields'].items()}
    reasons = []
    if listing.price_cents is not None:
        for rule in load_yaml(Path(__file__).with_name('hardware.yaml'))['offers']:
            limit = int(rule['max_eur'] * 100)
            price_ok = listing.price_cents < limit if rule.get('exclusive') else listing.price_cents <= limit
            if (price_ok and fields.get('platform') == rule['platform']
                    and (not rule.get('gpu') or fields.get('gpu') == rule['gpu'])
                    and not any(v['kind'] == 'conflict' for v in parsed['fields'].values())):
                reasons.append(rule['reason'])
    listing.attributes['offer_reasons'] = reasons
    return reasons
