"""Telegram keyboards and server-side resolution of compact callback identifiers."""
from __future__ import annotations

import re

from .watch import WATCH_STATE, watch_url

MENU_TEXT = {'📋 Mes suivis': '/suivis', '💰 Prix surveillés': '/prix',
             '🎮 Cartes graphiques': '/gpus', '❓ Aide': '/help'}
MENU_ROWS = [[{'text': '📋 Mes suivis', 'callback_data': 'cc:list:all'},
              {'text': '💰 Prix surveillés', 'callback_data': 'cc:list:price'}],
             [{'text': '🎮 Cartes graphiques', 'callback_data': 'cc:list:gpu'},
              {'text': '❓ Aide', 'callback_data': 'cc:help'}]]
REPLY_MENU = {'keyboard': [[{'text': '📋 Mes suivis'}, {'text': '💰 Prix surveillés'}],
                           [{'text': '🎮 Cartes graphiques'}, {'text': '❓ Aide'}]],
              'resize_keyboard': True, 'is_persistent': True,
              'input_field_placeholder': 'Choisir une action ou envoyer une commande'}


def remember_product(repo, namespace, url):
    try:
        url, ident = watch_url(url)
    except ValueError:
        return None
    if len(ident) > 20:
        return None
    repo.set_state(namespace, 'button_product:' + ident, url)
    return ident


def attach_buttons(repo, namespace, notification):
    rows = []
    ident = None
    if notification.url and not notification.metadata.get('watch_final'):
        ident = remember_product(repo, namespace, notification.url)
    if ident:
        rows = [[{'text': '🔗 Voir l’annonce', 'url': notification.url}],
                [{'text': '💰 Suivre le prix', 'callback_data': 'cc:price:' + ident},
                 {'text': '🔔 Disponibilité ×4', 'callback_data': 'cc:burst:' + ident}],
                [{'text': '🛑 Arrêter le suivi', 'callback_data': 'cc:stop:' + ident}]]
    for listed in notification.metadata.get('watch_ids', []):
        item = repo.state(namespace, 'watches', {}).get(listed)
        if item and remember_product(repo, namespace, item['url']):
            rows.append([{'text': '🔗 Article ' + listed, 'url': item['url']},
                         {'text': '🛑 Arrêter ' + listed, 'callback_data': 'cc:stop:' + listed}])
    if rows or notification.metadata.get('inline_menu'):
        notification.metadata['reply_markup'] = {'inline_keyboard': rows + MENU_ROWS}
    else:
        notification.metadata['reply_markup'] = REPLY_MENU


def callback_command(repo, namespace, data):
    menu = {'cc:help': '/help', 'cc:list:all': '/suivis', 'cc:list:price': '/prix',
            'cc:list:gpu': '/gpus'}
    if not isinstance(data, str):
        return None, 'Bouton inconnu. Utiliser /help.'
    if data in menu:
        return menu[data], None
    match = re.fullmatch(r'cc:(price|burst|stop):(\d{1,20})', data)
    if not match:
        return None, 'Bouton inconnu. Utiliser /help.'
    action, ident = match.groups()
    if action == 'stop':
        return '/arreter ' + ident, None
    item = repo.state(namespace, 'watches', {}).get(ident)
    url = item['url'] if item else repo.state(namespace, 'button_product:' + ident)
    if not url:
        return None, 'Ce bouton est trop ancien ou cet article est inconnu. Ajouter son lien avec /suivre ou /prix.'
    try:
        url, actual_ident = watch_url(url)
    except ValueError:
        return None, 'Le lien de ce bouton est invalide.'
    if actual_ident != ident:
        return None, 'L’article de ce bouton ne correspond plus au lien enregistré.'
    if repo.state(WATCH_STATE, url, {}).get('removed'):
        return None, 'Cet article a disparu du site. Son suivi a été supprimé.'
    return ('/prix ' if action == 'price' else '/suivre ') + url, None
