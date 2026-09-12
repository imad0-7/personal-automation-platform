"""Conservative deterministic extraction; evidence and ambiguity are first-class data."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from automation_platform.core.config import load_yaml
from automation_platform.core.models import Listing


def extract(text: str) -> dict:
    raw = unicodedata.normalize('NFKC', text).upper().replace('×', 'X')
    reference = load_yaml(Path(__file__).with_name('hardware.yaml'))
    result: dict = {'raw': text, 'fields': {}, 'questions': []}
    fields = result['fields']

    def put(key, value, evidence, kind='explicit'):
        if key in fields and fields[key]['value'] != value:
            fields[key] = {'value': None, 'evidence': 'Contradiction', 'kind': 'conflict'}
            result['questions'].append(f'{key} contradictoire')
        else:
            fields[key] = {'value': value, 'evidence': evidence, 'kind': kind}

    # Split glued units/model suffixes only after matching full CPU references.
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
        put('cpu', match.group(), match.group())
    for m in re.finditer(r'DDR\s*([345])', raw):
        put('ram_type', 'DDR' + m[1], m[0])
    platform = fields.get('platform', {}).get('value')
    if platform:
        put('ram_type', 'DDR5' if platform == 'AM5' else 'DDR4', platform, 'inferred')
    for m in re.finditer(r'(RTX|GTX|RX)\s*(\d{3,4})(?:\s*(TI|XT|XTX))?(?:\s*(SUPER))?', raw):
        put('gpu', ' '.join(x for x in m.groups() if x), m[0])
    if 'gpu' not in fields:
        result['questions'].append('Carte graphique non identifiée')
    for m in re.finditer(r'(\d)\s*X\s*(\d{1,3})\s*(?:GO|GB|G)(?![A-Z])', raw):
        put('ram_gb', int(m[1]) * int(m[2]), m[0], 'probable')
    if platform and 'ram_gb' not in fields:
        for m in re.finditer(r'(?<!\d)([1248])\s*X\s*(\d{1,3})(?!\d)', raw):
            if int(m[2]) in {4, 8, 16, 24, 32, 48, 64}:
                put('ram_gb', int(m[1]) * int(m[2]), m[0], 'probable')
    for m in re.finditer(r'(?:RAM\s*[:=-]?\s*)(\d{1,3})\s*(?:GO|GB|G)\b', raw):
        put('ram_gb', int(m[1]), m[0])
    storage = []
    seen_storage = set()
    for m in re.finditer(r'(SSD|NVME|HDD)\s*[:=-]?\s*(\d+(?:[.,]\d+)?)\s*(TO|TB|GO|GB)', raw):
        key = (m[1], m[2], m[3])
        if key not in seen_storage:
            storage.append({'type': m[1], 'capacity': m[2] + ' ' + m[3], 'evidence': m[0]})
            seen_storage.add(key)
    if storage:
        fields['storage'] = {'value': storage, 'kind': 'explicit', 'evidence': str(storage)}
    else:
        capacities = re.findall(r'(?<!\d)(\d+(?:[.,]\d+)?)\s*(?:TO|TB|T)(?![A-Z])', raw)
        if capacities:
            fields['storage'] = {'value': [{'type': 'inconnu', 'capacity': x + ' To'} for x in capacities],
                                 'kind': 'probable', 'evidence': 'Capacité seule, SSD/HDD inconnu'}
    if 'cpu' not in fields:
        result['questions'].append('Processeur non identifié')
    if fields.get('ram_gb', {}).get('kind') == 'probable':
        result['questions'].append('Confirmer que le multiplicateur désigne la RAM')
    return result


def analyze_listing(listing: Listing, correction: dict | None = None) -> list[str]:
    text = ' '.join([listing.title, str(listing.attributes.get('description', '')),
                     str(listing.attributes.get('features', {}))])
    parsed = extract(text)
    for key, value in (correction or {}).items():
        parsed['fields'][key] = {'value': value, 'kind': 'user', 'evidence': 'Correction personnelle'}
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
