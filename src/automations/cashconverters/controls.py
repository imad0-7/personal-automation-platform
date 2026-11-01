"""Single authorized subscriber today; preferences are scoped for future subscribers."""
from __future__ import annotations

import html
import re
import shlex

from automation_platform.core.models import Notification

from .buttons import MENU_TEXT, callback_command
from .watch import watch_command

DEFAULTS = {'mode': 'resume', 'reports': True}
HELP = (
    'AIDE ALFRED\n\n'
    '/help — rappeler les commandes\n'
    'Les boutons sous les alertes permettent de suivre un prix, activer les quatre alertes '
    'ou arrêter le suivi. Le menu donne accès aux listes et à l’aide.\n\n'
    'SUIVI D’ARTICLES\n'
    '/suivre LIEN — suivre un article Cash Converters (maximum 5)\n'
    '/suivis — voir tous les articles suivis et leurs derniers états\n'
    '/prix LIEN [LIEN…] — ajouter un ou plusieurs suivis de prix (maximum 20)\n'
    '/prix — afficher la liste des prix surveillés\n'
    '/gpus — afficher les cartes graphiques suivies automatiquement\n'
    '/arreter ID — arrêter un suivi (ID affiché dans /suivis)\n'
    'À chaque nouvelle disponibilité : quatre alertes 💰💰💰.\n\n'
    'SURVEILLANCE DES PC\n'
    '/mode tous — toutes les nouvelles annonces et les offres\n'
    '/mode offres — offres uniquement\n'
    '/mode resume — nouveautés regroupées et offres immédiates\n'
    '/mode pause — suspendre les alertes PC (les suivis restent actifs)\n'
    '/rapport on — activer le compte rendu à chaque scan\n'
    '/rapport off — désactiver le compte rendu systématique\n\n'
    '/status — état du moniteur et préférences\n'
    '/test — recevoir un message de test\n'
    '/corriger ID ram_gb=32 ram_type=DDR5 — corriger une annonce PC\n\n'
    'Commandes traitées au prochain scan, environ toutes les 15 minutes.'
)


def poll_commands(repo, notifier, namespace: str) -> None:
    if not hasattr(notifier, 'get_updates'):
        return
    offset = repo.state(namespace, 'telegram_offset', 0)
    for update in notifier.get_updates(offset):
        uid = update['update_id']
        if uid < offset:
            continue
        callback = update.get('callback_query')
        msg = (callback.get('message', {}) if callback else update.get('message', {}))
        chat = msg.get('chat', {})
        if (str(chat.get('id')) != notifier.chat_id or chat.get('type') != 'private'
                or callback and str(callback.get('from', {}).get('id')) != notifier.chat_id):
            repo.set_state(namespace, 'telegram_offset', uid + 1)
            continue
        prefs = repo.state(namespace, 'preferences', DEFAULTS.copy())
        callback_error = None
        if callback:
            text, callback_error = callback_command(repo, namespace, callback.get('data', ''))
            text = text or ''
            if hasattr(notifier, 'answer_callback'):
                notifier.answer_callback(callback['id'])
        else:
            text = msg.get('text', '').strip()
        text = MENU_TEXT.get(text, text)
        answer = callback_error or HELP
        if text in {'/help', '/start'}:
            answer = HELP
        elif text.startswith('/mode '):
            mode = text.split(maxsplit=1)[1].lower()
            if mode in {'tous', 'offres', 'resume', 'pause'}:
                prefs['mode'] = mode
                answer = f'Mode : {mode}'
        elif text in {'/rapport on', '/rapport off'}:
            prefs['reports'] = text.endswith(' on')
            answer = 'Compte rendu à chaque scan : ' + ('oui' if prefs['reports'] else 'non')
        elif text == '/test':
            answer = 'TEST : Alfred fonctionne. Ceci est un test, pas une nouvelle annonce.'
        elif text == '/status':
            answer = f"Mode : {prefs['mode']} — rapports : {prefs['reports']}\n"
            answer += str(repo.state('cashconverters-v2', 'last_status', 'Pas encore de scan V2'))
        elif text.split() and text.split()[0] in {'/suivre', '/suivis', '/arreter', '/prix', '/gpus'}:
            answer = watch_command(repo, namespace, text)
        elif text.startswith('/corriger '):
            try:
                args = shlex.split(text)
                ident = args[1]
                if repo.get_listing('cashconverters', ident) is None:
                    raise ValueError('Annonce inconnue')
                values = {}
                for arg in args[2:]:
                    key, value = arg.split('=', 1)
                    if key not in {'cpu', 'platform', 'gpu', 'ram_gb', 'ram_type'}:
                        raise ValueError('Champ non autorisé')
                    if key == 'ram_gb':
                        value = int(value)
                        if not 1 <= value <= 1024:
                            raise ValueError('Quantité de RAM invalide')
                    if key == 'platform' and value not in {'AM4', 'AM5', 'inconnu'}:
                        raise ValueError('Plateforme invalide')
                    if key == 'ram_type' and value not in {'DDR3', 'DDR4', 'DDR5', 'inconnu'}:
                        raise ValueError('Type de RAM invalide')
                    values[key] = value
                if not values:
                    raise ValueError('Aucune correction')
                current = repo.state(namespace, 'correction:' + ident, {})
                current.update(values)
                repo.set_state(namespace, 'correction:' + ident, current)
                queue = repo.state(namespace, 'review', {})
                queue.pop(ident, None)
                repo.set_state(namespace, 'review', queue)
                answer = 'Correction enregistrée pour cette annonce uniquement.'
            except (ValueError, IndexError):
                answer = 'Correction invalide. Exemple : /corriger 12345 ram_gb=32 ram_type=DDR5'
        repo.set_state(namespace, 'preferences', prefs)
        # Long watch lists can exceed Telegram's message limit; split before HTML escaping.
        chunk, chunks = '', []
        for line in answer.splitlines(keepends=True):
            for start in range(0, len(line), 1800):
                part = line[start:start + 1800]
                if len(chunk) + len(part) > 2600:
                    chunks.append(chunk)
                    chunk = ''
                chunk += part
        if chunk:
            chunks.append(chunk)
        for index, chunk in enumerate(chunks):
            repo.queue_event('cashconverters', f'{namespace}:command:{uid}:{index}',
                             Notification(title='ALFRED', message=html.escape(chunk), metadata={
                                 'inline_menu': True,
                                 'watch_ids': re.findall(r'^(\d+) — ', chunk, re.MULTILINE),
                             }))
        repo.set_state(namespace, 'telegram_offset', uid + 1)
