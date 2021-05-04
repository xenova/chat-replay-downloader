
from .common import (
    BaseChatDownloader,
    Chat,
    Remapper as r
)

from requests.exceptions import RequestException

from json.decoder import JSONDecodeError

from ..errors import (
    NoChatReplay,
    NoContinuation,
    ParsingError,
    VideoUnavailable,
    LoginRequired,
    VideoUnplayable,
    InvalidParameter
)

from urllib import parse

import json
import re

from ..utils import (
    try_get,
    multi_get,
    time_to_seconds,
    seconds_to_time,
    int_or_none,
    get_colours,
    try_get_first_key,
    try_get_first_value,
    remove_prefixes,
    remove_suffixes,
    camel_case_split,
    ensure_seconds,
    log,
    attempts,
    interruptable_sleep,
    try_parse_json
)

from datetime import datetime
from base64 import b64decode


class YouTubeChatDownloader(BaseChatDownloader):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    _NAME = 'youtube.com'

    _SITE_DEFAULT_PARAMS = {
        'format': 'youtube',
    }
    # _DEFAULT_FORMAT = ''

    # Regex provided by youtube-dl
    _VALID_URL = r'''(?x)^
                     (
                         # http(s):// or protocol-independent URL
                         (?:https?://|//)
                         (?:(?:(?:(?:\w+\.)?[yY][oO][uU][tT][uU][bB][eE](?:-nocookie|kids)?\.com/|
                            youtube\.googleapis\.com/)                        # the various hostnames, with wildcard subdomains
                         (?:.*?\#/)?                                          # handle anchor (#/) redirect urls
                         (?:                                                  # the various things that can precede the ID:
                             # v/ or embed/ or e/
                             (?:(?:v|embed|e)/(?!videoseries))
                             |(?:                                             # or the v= param in all its forms
                                 # preceding watch(_popup|.php) or nothing (like /?v=xxxx)
                                 (?:(?:watch|movie)(?:_popup)?(?:\.php)?/?)?
                                 (?:\?|\#!?)                                  # the params delimiter ? or # or #!
                                 # any other preceding param (like /?s=tuff&v=xxxx or ?s=tuff&amp;v=V36LpHqtcDY)
                                 (?:.*?[&;])??
                                 v=
                             )
                         ))
                         |(?:
                            youtu\.be                                        # just youtu.be/xxxx
                         )/)
                     )?                                                       # all until now is optional -> you can pass the naked ID
                     # here is it! the YouTube video ID
                     (?P<id>[0-9A-Za-z_-]{11})
                     # if we found the ID, everything can follow
                     (?(1).+)?
                     $'''

    _TESTS = [
        # Get top live streams
        # https://www.youtube.com/results?search_query&sp=CAMSAkAB


        # OTHER:
        # Japanese characters and lots of superchats
        # https://www.youtube.com/watch?v=UlemRwXYWHg

        # strange end times:
        # https://www.youtube.com/watch?v=DzEbfQI4TPQ
        # https://www.youtube.com/watch?v=7PPnCOhkxqo

        # purchased a product linked to the YouTube channel merchandising
        # https://youtu.be/y5ih7nqEoc4


        # TESTING FOR CORRECT FUNCIONALITY
        {
            'name': 'Get chat messages from livestream',
            'params': {
                'url': 'https://www.youtube.com/watch?v=5qap5aO4i9A',
                'timeout': 5
            }
        },
        {
            'name': 'Get chat messages from live chat replay',
            'params': {
                'url': 'https://www.youtube.com/watch?v=wXspodtIxYU',
                'max_messages': 10
            },

            'expected_result': {
                'message_types': ['text_message'],
                'action_types': ['add_chat_item'],
                'messages_condition': lambda messages: len(messages) > 0,
            }
        },
        {
            'name': 'Get superchat and ticker messages from live chat replay',
            'params': {
                'url': 'https://www.youtube.com/watch?v=UlemRwXYWHg',
                'end_time': 20,
                'message_groups': ['superchat', 'tickers']
            },

            'expected_result': {
                'message_types': ['paid_message', 'ticker_paid_message_item', 'membership_item', 'ticker_sponsor_item', 'paid_sticker', 'ticker_paid_sticker_item'],
                'action_types': ['add_chat_item', 'add_live_chat_ticker_item'],
                'messages_condition': lambda messages: len(messages) > 0,
            }
        },
        {
            'name': 'Get all messages from live chat replay',
            'params': {
                'url': 'https://www.youtube.com/watch?v=97w16cYskVI',
                'end_time': 50,
                'message_types': ['all']
            },

            'expected_result': {
                'message_types': ['viewer_engagement_message', 'paid_message', 'ticker_paid_message_item', 'text_message', 'paid_sticker', 'ticker_paid_sticker_item'],
                'action_types': ['add_chat_item', 'add_live_chat_ticker_item'],
                'messages_condition': lambda messages: len(messages) > 0,
            }
        },
        {
            'name': 'Get messages from top chat replay',
            'params': {
                'url': 'https://www.youtube.com/watch?v=zVCs9Cug_qM',
                'start_time': 0,
                'end_time': 20,
                'chat_type': 'top'
            },

            'expected_result': {
                'message_types': ['text_message'],
                'action_types': ['add_chat_item'],
                'messages_condition': lambda messages: len(messages) > 0,
            }
        },
        {
            'name': 'Chat replay with donations',
            'params': {
                'url': 'https://www.youtube.com/watch?v=Ih2WTyY62J4',
                'start_time': 0,
                'end_time': 40,
                'message_groups': ['donations']

            },

            'expected_result': {
                'message_types': ['donation_announcement'],
                'action_types': ['add_chat_item'],
                'messages_condition': lambda messages: len(messages) > 0,
            }
        },
        {
            # 874:24:05 current test
            'name': 'Get chat messages from an unplayable stream.',
            'params': {
                'url': 'https://www.youtube.com/watch?v=V2Afni3S-ok',
                'start_time': 10,
                'end_time': 100,
            },

            'expected_result': {
                'message_types': ['text_message'],
                'action_types': ['add_chat_item'],
                'messages_condition': lambda messages: len(messages) > 0,
            }
        },

        # TESTING FOR ERRORS
        {
            'name': 'Video does not exist',
            'params': {
                'url': 'https://www.youtube.com/watch?v=xxxxxxxxxxx',
            },
            'expected_result': {
                'error': VideoUnavailable,
            }
        },
        {
            'name': 'Members-only content',
            'params': {
                'url': 'https://www.youtube.com/watch?v=vprErlL1w2E',
            },
            'expected_result': {
                'error': VideoUnplayable,
            }
        },
        {
            'name': 'Chat is disabled for this live stream',
            'params': {
                'url': 'https://www.youtube.com/watch?v=XWq5kBlakcQ',
            },
            'expected_result': {
                'error': NoChatReplay,
            }
        },
        {
            'name': 'Live chat replay has been turned off for this video',
            'params': {
                'url': 'https://www.youtube.com/watch?v=7lGZvbasx6A',
            },
            'expected_result': {
                'error': NoChatReplay,
            }
        },
        {
            'name': 'Video is private',
            'params': {
                'url': 'https://www.youtube.com/watch?v=ijFMXqa-N0c',
            },
            'expected_result': {
                'error': LoginRequired,
            }
        },
        {
            'name': 'The uploader has not made this video available in your country.',
            'params': {
                'url': 'https://www.youtube.com/watch?v=sJL6WA-aGkQ',
            },
            'expected_result': {
                'error': VideoUnplayable,
            }
        }
    ]

    _YT_INITIAL_DATA_RE = r'(?:window\s*\[\s*["\']ytInitialData["\']\s*\]|ytInitialData)\s*=\s*({.+?})\s*;'
    _YT_INITIAL_PLAYER_RESPONSE_RE = r'ytInitialPlayerResponse\s*=\s*({.+?})\s*;'

    _YT_HOME = 'https://www.youtube.com'
    _YT_VIDEO_TEMPLATE = _YT_HOME + '/watch?v={}'

    _YOUTUBE_INIT_API_TEMPLATE = _YT_HOME + '/{}?continuation={}'
    _YOUTUBE_CHAT_API_TEMPLATE = _YT_HOME + \
        b64decode(
            'L3lvdXR1YmVpL3YxL2xpdmVfY2hhdC9nZXRfe30/a2V5PUFJemFTeUFPX0ZKMlNscVU4UTRTVEVITEdDaWx3X1k5XzExcWNXOA==').decode()

    _MESSAGE_GROUPS = {
        'messages': [
            'text_message'  # normal message
        ],
        'superchat': [
            # superchat messages which appear in chat
            'membership_item',
            'paid_message',
            'paid_sticker',
        ],
        'tickers': [
            # superchat messages which appear ticker (at the top)
            'ticker_paid_sticker_item',
            'ticker_paid_message_item',
            'ticker_sponsor_item',
        ],
        'banners': [
            'banner',
            'banner_header'
        ],

        'donations': [
            'donation_announcement'
        ],
        'engagement': [
            # message saying live chat replay is on
            'viewer_engagement_message',
        ],
        'purchases': [
            'purchased_product_message'  # product purchased
        ],

        'mode_changes': [
            'mode_change_message'  # e.g. slow mode enabled
        ],

        'deleted': [
            'deleted_message'
        ],
        'bans': [
            'ban_user'
        ],

        'placeholder': [
            'placeholder_item'  # placeholder
        ]
    }

    _MESSAGE_TYPES = ['all']
    for group in _MESSAGE_GROUPS:
        _MESSAGE_TYPES += _MESSAGE_GROUPS[group]

    @staticmethod
    def get_source_image_url(url):
        index = url.find('=')
        if index >= 0:
            return url[0:url.index('=')]
        else:
            return url

    @ staticmethod
    def parse_youtube_link(text):
        if text.startswith(('/redirect', 'https://www.youtube.com/redirect')):  # is a redirect link
            info = dict(parse.parse_qsl(parse.urlsplit(text).query))
            return info.get('q') or ''
        elif text.startswith('//'):
            return 'https:' + text
        elif text.startswith('/'):  # is a youtube link e.g. '/watch','/results'
            return YouTubeChatDownloader._YT_HOME + text
        else:  # is a normal link
            return text

    @ staticmethod
    def parse_navigation_endpoint(navigation_endpoint, default_text=''):

        url = try_get(navigation_endpoint, lambda x: YouTubeChatDownloader.parse_youtube_link(
            x['commandMetadata']['webCommandMetadata']['url'])) or default_text

        return url

    @ staticmethod
    def parse_runs(run_info, parse_links=True):
        """ Reads and parses YouTube formatted messages (i.e. runs). """

        message_info = {
            'message': ''
        }
        message_emotes = {}

        runs = run_info.get('runs') or []
        for run in runs:
            if 'text' in run:
                if parse_links and 'navigationEndpoint' in run:  # is a link and must parse

                    # if something fails, use default text
                    message_info['message'] += YouTubeChatDownloader.parse_navigation_endpoint(
                        run['navigationEndpoint'], run['text'])

                else:  # is a normal message
                    message_info['message'] += run['text']
            elif 'emoji' in run:
                emoji = run['emoji']
                emoji_id = emoji['emojiId']

                name = emoji['shortcuts'][0]

                if emoji_id and emoji_id not in message_emotes:
                    message_emotes[emoji_id] = {
                        'id': emoji_id,
                        'name': name,
                        'shortcuts': emoji['shortcuts'],
                        'search_terms': emoji['searchTerms'],
                        'images': YouTubeChatDownloader.parse_thumbnails(emoji['image']),
                        'is_custom_emoji': emoji['isCustomEmoji']
                    }

                message_info['message'] += name

            else:
                # unknown run
                message_info['message'] += str(run)

        if message_emotes:
            message_info['emotes'] = list(message_emotes.values())

        return message_info

    @ staticmethod
    def _parse_item(item, info=None):
        if info is None:
            info = {}
        # info is starting point
        item_index = try_get_first_key(item)
        item_info = item.get(item_index)

        if not item_info:
            return info

        for key in item_info:
            BaseChatDownloader.remap(
                info, YouTubeChatDownloader._REMAPPING, key, item_info[key])

        # check for colour information
        for colour_key in YouTubeChatDownloader._COLOUR_KEYS:
            if colour_key in item_info:  # if item has colour information
                info[camel_case_split(colour_key.replace('Color', 'Colour'))] = get_colours(
                    item_info[colour_key]).get('hex')

        item_endpoint = item_info.get('showItemEndpoint')
        if item_endpoint:  # has additional information
            renderer = multi_get(
                item_endpoint, 'showLiveChatItemEndpoint', 'renderer')

            if renderer:
                info.update(YouTubeChatDownloader._parse_item(renderer))

        BaseChatDownloader.move_to_dict(info, 'author')

        # TODO determine if youtube glitch has occurred
        # round(time_in_seconds/timestamp) == 1
        time_in_seconds = info.get('time_in_seconds')
        time_text = info.get('time_text')

        if time_in_seconds is not None:

            if time_text is not None:
                # All information was provided, check if time_in_seconds is <= 0
                # For some reason, YouTube sets the video offset to 0 if the message
                # was sent before the stream started. This fixes that:
                if time_in_seconds <= 0:
                    info['time_in_seconds'] = time_to_seconds(time_text)
            else:
                # recreate time text from time in seconds
                info['time_text'] = seconds_to_time(int(time_in_seconds))

        elif time_text is not None:  # doesn't have time in seconds, but has time text
            info['time_in_seconds'] = time_to_seconds(time_text)
        else:
            pass
            # has no current video time information
            # (usually live video or a sub-item)

        return info

    @ staticmethod
    def parse_badges(badge_items):
        badges = []

        for badge in badge_items:
            to_add = {}
            parsed_badge = YouTubeChatDownloader._parse_item(badge)

            title = parsed_badge.pop('tooltip', None)
            if title:
                to_add['title'] = title

            icon = parsed_badge.pop('icon', None)
            if icon:
                to_add['icon_name'] = icon.lower()

            badge_icons = parsed_badge.pop('badge_icons', None)
            if badge_icons:
                to_add['icons'] = []

                url = None
                for icon in badge_icons:
                    url = icon.get('url')
                    if url:
                        matches = re.search(r'=s(\d+)', url)
                        if matches:
                            size = int(matches.group(1))
                            to_add['icons'].append(
                                BaseChatDownloader.create_image(url, size, size))
                if url:
                    to_add['icons'].insert(0, BaseChatDownloader.create_image(
                        YouTubeChatDownloader.get_source_image_url(url), image_id='source'))

            badges.append(to_add)

            # if 'member'
            # remove the tooltip afterwards
            # print(badges)
        return badges

    @ staticmethod
    def parse_thumbnails(item):

        # sometimes thumbnails come as a list
        if isinstance(item, list):
            item = item[0]  # rebase

        # TODO add source:
        # https://yt3.ggpht.com/ytc/AAUvwnhBYeK7_iQTJbXe6kIMpMlCI2VsVHhb6GBJuYeZ=s32-c-k-c0xffffffff-no-rj-mo
        # https://yt3.ggpht.com/ytc/AAUvwnhBYeK7_iQTJbXe6kIMpMlCI2VsVHhb6GBJuYeZ

        thumbnails = item.get('thumbnails') or []
        final = list(map(lambda x: BaseChatDownloader.create_image(
            x.get('url'),
            x.get('width'),
            x.get('height'),
        ), thumbnails))

        if len(final) > 0:
            final.insert(0, BaseChatDownloader.create_image(
                YouTubeChatDownloader.get_source_image_url(final[0]['url']), image_id='source'))

        return final

    @ staticmethod
    def parse_action_button(item):
        return {
            'url': try_get(item, lambda x: YouTubeChatDownloader.parse_navigation_endpoint(x['buttonRenderer']['navigationEndpoint'])) or '',
            'text': multi_get(item, 'buttonRenderer', 'text', 'simpleText') or ''
        }

    @staticmethod
    def get_simple_text(item):
        return item.get('simpleText')

    _CURRENCY_SYMBOLS = {
        '$': 'USD',
        'A$': 'AUD',
        'CA$': 'CAD',
        'HK$': 'HKD',
        'MX$': 'MXN',
        'NT$': 'TWD',
        'NZ$': 'NZD',
        'R$': 'BRL',
        '£': 'GBP',
        '€': 'EUR',
        '₹': 'INR',

        '₩': 'KRW',
        '￦': 'KRW',

        '¥': 'JPY',
        '￥': 'JPY',
    }

    # All other currency symbols use the ISO 4217 format:
    # https://en.wikipedia.org/wiki/ISO_4217
    # e.g. 'CHF', 'COP', 'HUF', 'PHP', 'PLN', 'RUB', 'SEK', 'PEN', 'ARS', 'CLP', 'NOK', 'BAM', 'SGD'

    @staticmethod
    def parse_currency(item):
        mixed_text = item.get('simpleText') or str(item)

        info = re.split(r'([\d,\.]+)', mixed_text)
        if len(info) >= 2:  # Correct parse
            currency_symbol = info[0].strip()
            currency_code = YouTubeChatDownloader._CURRENCY_SYMBOLS.get(
                currency_symbol, currency_symbol)
            amount = float(info[1].replace(',', ''))

        else:  # Unable to get info
            amount = float(re.sub(r'[^\d\.]+', '', mixed_text))
            currency_symbol = currency_code = None

        return {
            'text': mixed_text,
            'amount': amount,
            'currency': currency_code,  # ISO_4217
            'currency_symbol': currency_symbol
        }

    _REMAPPING = {
        'id': 'message_id',
        'authorExternalChannelId': 'author_id',
        'authorName': r('author_name', get_simple_text),
        # TODO author_display_name
        'purchaseAmountText': r('money', parse_currency),
        'message': r(None, parse_runs, True),
        'timestampText': r('time_text', get_simple_text),
        'timestampUsec': r('timestamp', int_or_none),

        'authorPhoto': r('author_images', parse_thumbnails),

        'tooltip': 'tooltip',

        'icon': r('icon', lambda x: x.get('iconType')),
        'authorBadges': r('author_badges', parse_badges),

        # stickers
        'sticker': r('sticker_images', parse_thumbnails),

        # ticker_paid_message_item
        'fullDurationSec': r('ticker_duration', int_or_none),
        'amount': r('money', parse_currency),


        # ticker_sponsor_item
        'detailText': r(None, parse_runs, True),
        'customThumbnail': r('badge_icons', parse_thumbnails),

        # membership_item
        'headerSubtext': r(None, parse_runs, True),
        'sponsorPhoto': r('sponsor_icons', parse_thumbnails),

        # ticker_paid_sticker_item
        'tickerThumbnails': r('ticker_icons', parse_thumbnails),

        # deleted messages
        'deletedStateMessage': r(None, parse_runs, True),
        'targetItemId': 'target_message_id',

        'externalChannelId': 'author_id',

        # action buttons
        'actionButton': r('action', parse_action_button),

        # addBannerToLiveChatCommand
        'text': r(None, parse_runs, True),
        'viewerIsCreator': 'viewer_is_creator',
        'targetId': 'target_message_id',
        'isStackable': 'is_stackable',

        # removeBannerForLiveChatCommand
        'targetActionId': 'target_message_id',

        # donation_announcement
        'subtext': r(None, parse_runs, True),

        # tooltip
        'detailsText': r(None, parse_runs, True),

    }

    _COLOUR_KEYS = [
        # paid_message
        'authorNameTextColor', 'timestampColor', 'bodyBackgroundColor',
        'headerTextColor', 'headerBackgroundColor', 'bodyTextColor',

        # paid_sticker
        'backgroundColor', 'moneyChipTextColor', 'moneyChipBackgroundColor',

        # ticker_paid_message_item
        'startBackgroundColor', 'amountTextColor', 'endBackgroundColor',

        # ticker_sponsor_item
        'detailTextColor'
    ]

    _STICKER_KEYS = [
        # to actually ignore
        'stickerDisplayWidth', 'stickerDisplayHeight',  # ignore

        # parsed elsewhere
        'sticker',
    ]

    _KEYS_TO_IGNORE = [
        # to actually ignore
        'contextMenuAccessibility', 'contextMenuEndpoint', 'trackingParams', 'accessibility',

        'contextMenuButton',

        # parsed elsewhere
        'showItemEndpoint',
        'durationSec',

        # banner parsed elsewhere
        'header', 'contents', 'actionId',

        # tooltipRenderer
        'dismissStrategy', 'suggestedPosition', 'promoConfig'
    ]

    _KNOWN_KEYS = set(list(_REMAPPING.keys()) +
                      _COLOUR_KEYS + _STICKER_KEYS + _KEYS_TO_IGNORE)

    # KNOWN ACTIONS AND MESSAGE TYPES
    _KNOWN_ADD_TICKER_TYPES = {
        'addLiveChatTickerItemAction': [
            'liveChatTickerSponsorItemRenderer',
            'liveChatTickerPaidStickerItemRenderer',
            'liveChatTickerPaidMessageItemRenderer'
        ]
    }

    _KNOWN_ADD_ACTION_TYPES = {
        'addChatItemAction': [
            # message saying Live Chat replay is on
            'liveChatViewerEngagementMessageRenderer',
            'liveChatMembershipItemRenderer',
            'liveChatTextMessageRenderer',
            'liveChatPaidMessageRenderer',
            'liveChatPlaceholderItemRenderer',  # placeholder
            'liveChatDonationAnnouncementRenderer',

            'liveChatPaidStickerRenderer',
            'liveChatModeChangeMessageRenderer',  # e.g. slow mode enabled

            # TODO find examples of:
            # 'liveChatPurchasedProductMessageRenderer',  # product purchased
            # liveChatLegacyPaidMessageRenderer
            # liveChatModerationMessageRenderer
            # liveChatAutoModMessageRenderer

        ]
    }

    _KNOWN_REPLACE_ACTION_TYPES = {
        'replaceChatItemAction': [
            'liveChatPlaceholderItemRenderer',
            'liveChatTextMessageRenderer'
        ]
    }

    # actions that have an 'item'
    _KNOWN_ITEM_ACTION_TYPES = {
        **_KNOWN_ADD_TICKER_TYPES, **_KNOWN_ADD_ACTION_TYPES}

    # [message deleted] or [message retracted]
    _KNOWN_REMOVE_ACTION_TYPES = {
        'markChatItemsByAuthorAsDeletedAction': [  # TODO ban?
            'banUser'  # deletedStateMessage
        ],
        'markChatItemAsDeletedAction': [
            'deletedMessage'  # deletedStateMessage
        ]
    }

    _KNOWN_ADD_BANNER_TYPES = {
        'addBannerToLiveChatCommand': [
            'liveChatBannerRenderer',
            'liveChatBannerHeaderRenderer'
            'liveChatTextMessageRenderer'
        ]
    }

    _KNOWN_REMOVE_BANNER_TYPES = {
        'removeBannerForLiveChatCommand': [
            'removeBanner'  # targetActionId
        ]
    }

    _KNOWN_TOOLTIP_ACTION_TYPES = {
        'showLiveChatTooltipCommand': [
            'tooltipRenderer'
        ]
    }

    # Not come across yet (actions/commands)
    # search "livechat"
    # https://github.com/reachomk/ytvanced/tree/master/src/main/java/com/google/protos/youtube/api/innertube
    # addLiveChatTextMessageFromTemplateAction
    # liveChatMessageBuyFlowHeadingRenderer
    # liveChatPaidMessageFooterRenderer
    # liveChatProductButtonRenderer
    # liveChatPurchaseMessageEndpoint
    # removeChatItemAction
    # replaceLiveChatRendererAction
    # showLiveChatDialogAction
    # showLiveChatSurveyCommand

    # Not checked for
    # _KNOWN_IGNORE_ACTION_TYPES = {
    #     'authorBadges': [
    #         'liveChatAuthorBadgeRenderer'
    #     ],
    #     'showLiveChatItemEndpoint': [
    #         'liveChatPaidStickerRenderer',
    #         'liveChatPaidMessageRenderer',
    #         'liveChatMembershipItemRenderer'
    #     ]
    # }

    _KNOWN_POLL_ACTION_TYPES = {
    }

    _KNOWN_IGNORE_ACTION_TYPES = {

        # TODO add support for poll actions
        'showLiveChatActionPanelAction': [],
        'updateLiveChatPollAction': [],
        'closeLiveChatActionPanelAction': []

    }

    _KNOWN_ACTION_TYPES = {
        **_KNOWN_ITEM_ACTION_TYPES,
        **_KNOWN_REMOVE_ACTION_TYPES,
        **_KNOWN_REPLACE_ACTION_TYPES,
        **_KNOWN_ADD_BANNER_TYPES,
        **_KNOWN_REMOVE_BANNER_TYPES,
        **_KNOWN_TOOLTIP_ACTION_TYPES,
        **_KNOWN_POLL_ACTION_TYPES,
        **_KNOWN_IGNORE_ACTION_TYPES
    }

    _KNOWN_IGNORE_MESSAGE_TYPES = [
        'liveChatPlaceholderItemRenderer'
    ]
    _KNOWN_MESSAGE_TYPES = []
    for action in _KNOWN_ACTION_TYPES:
        _KNOWN_MESSAGE_TYPES += _KNOWN_ACTION_TYPES[action]

    _KNOWN_SEEK_CONTINUATIONS = [
        'playerSeekContinuationData'
    ]

    _KNOWN_CHAT_CONTINUATIONS = [
        'invalidationContinuationData', 'timedContinuationData',
        'liveChatReplayContinuationData', 'reloadContinuationData'
    ]

    _KNOWN_CONTINUATIONS = _KNOWN_SEEK_CONTINUATIONS + _KNOWN_CHAT_CONTINUATIONS

    @staticmethod
    def generate_urls(**kwargs):
        downloader = YouTubeChatDownloader()
        items = downloader.get_testing_items()

        for item in items:
            yield YouTubeChatDownloader._YT_VIDEO_TEMPLATE.format(item['video_id'])
        # print('b')

        # downloader.get_playlist_items

    _LIVE_PLAYLIST_URL = _YT_HOME + '/channel/UC4R8DWoMoI7CAwX8_LjQHig'

    def get_testing_items(self):

        html, yt_info = self._get_initial_info(self._LIVE_PLAYLIST_URL)

        sections = yt_info['contents']['twoColumnBrowseResultsRenderer']['tabs'][
            0]['tabRenderer']['content']['sectionListRenderer']['contents']

        for section in sections:
            section_info = section['itemSectionRenderer']['contents'][0]['shelfRenderer']

            # print(section_info)

            # section_title = section_info['title']['runs'][0]['text']
            # print(section_title)

            # items = section_info['content']['horizontalListRenderer']['items']

            playlist_url = self._YT_HOME + \
                section_info['endpoint']['commandMetadata']['webCommandMetadata']['url']

            yield from self.get_playlist_items(playlist_url)

    def get_playlist_items(self, playlist_url):

        html, yt_info = self._get_initial_info(playlist_url)

        items = yt_info['contents']['twoColumnBrowseResultsRenderer']['tabs'][0]['tabRenderer']['content'][
            'sectionListRenderer']['contents'][0]['itemSectionRenderer']['contents'][0]['playlistVideoListRenderer']['contents']

        for item in items:
            playlist_video = item.get('playlistVideoRenderer')

            if playlist_video:
                # print(playlist_video)

                item = {
                    'video_id': playlist_video.get('videoId'),
                    'title': self.parse_runs(playlist_video.get('title'))['message'],
                }

                yield item

            # "continuationItemRenderer":{
            #     "trigger":"CONTINUATION_TRIGGER_ON_ITEM_SHOWN",
            #     "continuationEndpoint":{
            #         "clickTrackingParams":"CCgQ7zsYACITCNT0zMKim-4CFU-V1QodgR4KyA==",
            #         "commandMetadata":{
            #             "webCommandMetadata":{
            #             "sendPost":true,
            #             "apiUrl":"/youtubei/v1/browse"
            #             }
            #         },
            #         "continuationCommand":{
            #             "token":"4qmFsgJhEiRWTFBMRXJ1a1gxVzFPWWpGeDJwRzh6aldpTXVQTUcwRi1MYkkaFENBRjZCbEJVT2tOSFVRJTNEJTNEmgIiUExFcnVrWDFXMU9ZakZ4MnBHOHpqV2lNdVBNRzBGLUxiSQ%3D%3D",
            #             "request":"CONTINUATION_REQUEST_TYPE_BROWSE"
            #         }
            #     }
            # }

    def _get_initial_info(self, url):
        html = self._session_get(url, cookies={'CONSENT': 'PENDING+999'}).text #cookies param to ignore YouTube cookie consent page
        yt = re.search(self._YT_INITIAL_DATA_RE, html)
        yt_initial_data = try_parse_json(yt.group(1)) if yt else None
        return html, yt_initial_data

    def _get_initial_video_info(self, video_id):
        """ Get initial YouTube video information. """
        original_url = self._YT_VIDEO_TEMPLATE.format(video_id)

        html, yt_initial_data = self._get_initial_info(original_url)

        if not yt_initial_data:  # Fatal error
            raise ParsingError(
                'Unable to parse initial video data. {}'.format(html))

        player_response = re.search(self._YT_INITIAL_PLAYER_RESPONSE_RE, html)
        player_response_info = try_parse_json(
            player_response.group(1)) if player_response else None

        if not player_response_info:
            log('warning', 'Unable to parse player response, proceeding with caution: {}'.format(html))
            player_response_info = {}

        streaming_data = player_response_info.get('streamingData') or {}
        formats = streaming_data.get(
            'adaptiveFormats') or streaming_data.get('formats')
        last_modified = try_get(formats, lambda x: float(x[0]['lastModified']))

        details = {
            'start_time': last_modified,
            'visitor_data': multi_get(yt_initial_data, 'responseContext', 'webResponseContextExtensionData', 'ytConfigData', 'visitorData')
        }

        # Try to get continuation info
        contents = yt_initial_data.get('contents') or {}

        conversation_bar = multi_get(
            contents, 'twoColumnWatchNextResults', 'conversationBar')
        sub_menu_items = multi_get(conversation_bar, 'liveChatRenderer', 'header', 'liveChatHeaderRenderer',
                                   'viewSelector', 'sortFilterSubMenuRenderer', 'subMenuItems') or {}
        details['continuation_info'] = {
            x['title']: x['continuation']['reloadContinuationData']['continuation']
            for x in sub_menu_items
        }
        details['is_live'] = 'Live chat' in details['continuation_info']

        playability_status = player_response_info.get(
            'playabilityStatus') or {}
        status = playability_status.get('status')
        error_screen = playability_status.get('errorScreen')

        # Only raise an error if there is no continuation info. Sometimes you
        # are able to view chat, but not the video (e.g. for very long livestreams)
        if not details['continuation_info']:
            if error_screen:  # There is a error screen visible
                error_reasons = {
                    'reason': '',
                    'subreason': '',
                }
                error_info = try_get_first_value(error_screen)

                for error_reason in error_reasons:
                    text = error_info.get(error_reason) or {}

                    error_reasons[error_reason] = text.get('simpleText') or try_get(
                        text, lambda x: self.parse_runs(x, False)['message']) or error_info.pop(
                        'itemTitle', '') or error_info.pop(
                            'offerDescription', '') or playability_status.get(error_reason) or ''

                error_message = ''
                for error_reason in error_reasons:
                    if error_reasons[error_reason]:
                        if isinstance(error_reasons[error_reason], str):
                            error_message += ' {}.'.format(
                                error_reasons[error_reason].rstrip('.'))
                        else:
                            error_message += str(error_reasons[error_reason])

                error_message = error_message.strip()

                if status == 'ERROR':
                    raise VideoUnavailable(error_message)
                elif status == 'LOGIN_REQUIRED':
                    raise LoginRequired(error_message)
                elif status == 'UNPLAYABLE':
                    raise VideoUnplayable(error_message)
                else:
                    log('debug', 'Unknown status: {}. {}'.format(
                        status, playability_status))
                    error_message = '{}: {}'.format(status, error_message)
                    raise VideoUnavailable(error_message)
            elif not contents:
                raise VideoUnavailable(
                    'Unable to find initial video contents.')
            else:
                # Video exists, but you cannot view chat for some reason
                error_message = try_get(conversation_bar, lambda x: self.parse_runs(
                    x['conversationBarRenderer']['availabilityMessage']['messageRenderer']['text'], False)['message']) or \
                    'Video does not have a chat replay.'
                raise NoChatReplay(error_message)

        video_details = player_response_info.get('videoDetails') or {}
        details['title'] = video_details.get('title')
        details['duration'] = int_or_none(video_details.get('lengthSeconds'))
        return details

    def _get_chat_messages(self, initial_info, params):

        initial_continuation_info = initial_info.get('continuation_info') or {}

        # stream_start_time = initial_info.get('start_time')
        is_live = initial_info.get('is_live')
        visitor_data = initial_info.get('visitor_data')

        # duration = initial_info.get('duration')

        start_time = ensure_seconds(params.get('start_time'))
        end_time = ensure_seconds(params.get('end_time'))

        # Top chat replay - Some messages, such as potential spam, may not be visible
        # Live chat replay - All messages are visible
        chat_type = params.get('chat_type').title()  # Live or Top

        continuation_values = list(initial_continuation_info.values())
        continuation_keys = list(initial_continuation_info.keys())
        if len(continuation_values) < 2:
            raise NoContinuation(
                'Initial continuation information could not be found.'.format(initial_continuation_info))

        continuation_index = 0 if chat_type == 'Top' else 1
        continuation = continuation_values[continuation_index]
        log('debug', 'Getting {} chat ({}).'.format(
            chat_type, continuation_keys[continuation_index]))

        api_type = 'live_chat'
        if not is_live:
            api_type += '_replay'

        init_page = self._YOUTUBE_INIT_API_TEMPLATE.format(
            api_type, continuation)
        # must run to get first few messages, otherwise might miss some
        html, yt_info = self._get_initial_info(init_page)

        continuation_url = self._YOUTUBE_CHAT_API_TEMPLATE.format(api_type)
        continuation_params = {
            'context': {
                'client': {
                    'visitorData': visitor_data,
                    'userAgent': self.get_session_headers('User-Agent'),
                    'clientName': 'WEB',
                    'clientVersion': '2.{}.01.00'.format(datetime.today().strftime('%Y%m%d'))
                }
            }
        }

        offset_milliseconds = (
            start_time * 1000) if isinstance(start_time, int) else None

        # force_no_timeout = params.get('force_no_timeout')

        max_attempts = params.get('max_attempts')
        retry_timeout = params.get('retry_timeout')

        messages_groups_to_add = params.get('message_groups') or []
        messages_types_to_add = params.get('message_types') or []

        invalid_groups = set(messages_groups_to_add) - \
            self._MESSAGE_GROUPS.keys()
        if 'all' not in messages_groups_to_add and invalid_groups:
            raise InvalidParameter(
                'Invalid groups specified: {}'.format(invalid_groups))

        self.check_for_invalid_types(
            messages_types_to_add, self._MESSAGE_TYPES)

        message_count = 0
        first_time = True
        while True:
            info = None
            for attempt_number in attempts(max_attempts):

                try:

                    if not first_time:

                        continuation_params['continuation'] = continuation

                        if not is_live and offset_milliseconds is not None:
                            continuation_params['currentPlayerState'] = {
                                'playerOffsetMs': offset_milliseconds}

                        log('debug', 'Continuation: {}'.format(continuation))

                        yt_info = self._session_post(
                            continuation_url, json=continuation_params).json()

                    info = multi_get(
                        yt_info, 'continuationContents', 'liveChatContinuation')

                    if not info:
                        return

                    break  # successful retrieve

                except (JSONDecodeError, RequestException) as e:
                    self.retry(attempt_number, max_attempts, e, retry_timeout)
                    self.clear_cookies()

                    continue

            actions = info.get('actions') or []

            # print(actions)

            if actions:
                for action in actions:
                    # print(action)
                    data = {}

                    # if it is a replay chat item action, must re-base it
                    replay_chat_item_action = action.get(
                        'replayChatItemAction')
                    if replay_chat_item_action:
                        offset_time = replay_chat_item_action.get(
                            'videoOffsetTimeMsec')
                        if offset_time:
                            data['time_in_seconds'] = float(offset_time) / 1000

                        action = replay_chat_item_action['actions'][0]

                    action.pop('clickTrackingParams', None)
                    original_action_type = try_get_first_key(action)

                    data['action_type'] = camel_case_split(
                        remove_suffixes(original_action_type, ('Action', 'Command')))

                    original_message_type = None
                    original_item = {}

                    # We now parse the info and get the message
                    # type based on the type of action
                    if original_action_type in self._KNOWN_ITEM_ACTION_TYPES:
                        original_item = multi_get(
                            action, original_action_type, 'item')

                        original_message_type = try_get_first_key(
                            original_item)
                        data = self._parse_item(original_item, data)

                    elif original_action_type in self._KNOWN_REMOVE_ACTION_TYPES:
                        original_item = action
                        if original_action_type == 'markChatItemAsDeletedAction':
                            original_message_type = 'deletedMessage'
                        else:  # markChatItemsByAuthorAsDeletedAction
                            original_message_type = 'banUser'

                        data = self._parse_item(original_item, data)

                    elif original_action_type in self._KNOWN_REPLACE_ACTION_TYPES:
                        original_item = multi_get(
                            action, original_action_type, 'replacementItem')

                        original_message_type = try_get_first_key(
                            original_item)
                        data = self._parse_item(original_item, data)

                    elif original_action_type in self._KNOWN_TOOLTIP_ACTION_TYPES:
                        original_item = multi_get(
                            action, original_action_type, 'tooltip')

                        original_message_type = try_get_first_key(
                            original_item)
                        data = self._parse_item(original_item, data)

                    elif original_action_type in self._KNOWN_ADD_BANNER_TYPES:
                        original_item = multi_get(
                            action, original_action_type, 'bannerRenderer')

                        if original_item:
                            original_message_type = try_get_first_key(
                                original_item)

                            header = original_item[original_message_type].get(
                                'header')
                            parsed_header = self._parse_item(header)
                            header_message = parsed_header.get('message')

                            contents = original_item[original_message_type].get(
                                'contents')
                            parsed_contents = self._parse_item(contents)

                            data.update(parsed_header)
                            data.update(parsed_contents)
                            data['header_message'] = header_message
                        else:
                            self.debug_log(params,
                                           'No bannerRenderer item',
                                           'Action type: {}'.format(
                                               original_action_type),
                                           'Action: {}'.format(action),
                                           'Parsed data: {}'.format(data)
                                           )

                    elif original_action_type in self._KNOWN_REMOVE_BANNER_TYPES:
                        original_item = action
                        original_message_type = 'removeBanner'
                        data = self._parse_item(original_item, data)

                    elif original_action_type in self._KNOWN_IGNORE_ACTION_TYPES:
                        continue
                        # ignore these
                    else:
                        # not processing these
                        self.debug_log(params,
                                       'Unknown action: {}'.format(
                                           original_action_type),
                                       action,
                                       data
                                       )

                    test_for_missing_keys = original_item.get(
                        original_message_type, {}).keys()
                    missing_keys = test_for_missing_keys - self._KNOWN_KEYS

                    # print(action)
                    if not data:  # TODO debug
                        self.debug_log(params,
                                       'Parse of action returned empty results: {}'.format(
                                           original_action_type),
                                       action
                                       )

                    if missing_keys:  # TODO debugging for missing keys
                        self.debug_log(params,
                                       'Missing keys found: {}'.format(
                                           missing_keys),
                                       'Message type: {}'.format(
                                           original_message_type),
                                       'Action type: {}'.format(
                                           original_action_type),
                                       'Action: {}'.format(action),
                                       'Parsed data: {}'.format(data)
                                       )

                    if original_message_type:

                        new_index = remove_prefixes(
                            original_message_type, 'liveChat')
                        new_index = remove_suffixes(new_index, 'Renderer')
                        data['message_type'] = camel_case_split(new_index)

                        # TODO add option to keep placeholder items
                        if original_message_type in self._KNOWN_IGNORE_MESSAGE_TYPES:
                            continue
                            # skip placeholder items
                        elif original_message_type not in self._KNOWN_ACTION_TYPES[original_action_type]:
                            self.debug_log(params,
                                           'Unknown message type "{}" for action "{}"'.format(
                                               original_message_type,
                                               original_action_type
                                           ),
                                           'New message type: {}'.format(
                                               data['message_type']),
                                           'Action: {}'.format(action),
                                           'Parsed data: {}'.format(data)
                                           )

                    else:  # no type # can ignore message
                        self.debug_log(params,
                                       'No message type',
                                       'Action type: {}'.format(
                                           original_action_type),
                                       'Action: {}'.format(action),
                                       'Parsed data: {}'.format(data)
                                       )
                        continue

                    # check whether to skip this message or not, based on its type

                    to_add = self.must_add_item(
                        data,
                        self._MESSAGE_GROUPS,
                        messages_groups_to_add,
                        messages_types_to_add
                    )

                    if not to_add:
                        continue

                    # if from a replay, check whether to skip this message or not, based on its time
                    if not is_live:
                        # assume message is at beginning if it does not have a time component
                        time_in_seconds = data.get('time_in_seconds', 0)

                        before_start = start_time is not None and time_in_seconds < start_time
                        after_end = end_time is not None and time_in_seconds > end_time

                        if first_time and before_start:
                            continue  # first time and invalid start time
                        elif before_start or after_end:
                            return  # while actually searching, if time is invalid

                    # try to reconstruct time in seconds from timestamp and stream start
                    # if data.get('time_in_seconds') is None and data.get('timestamp') is not None:
                    #     data['time_in_seconds'] = (data['timestamp'] - stream_start_time)/1e6
                    #     data['time_text'] = seconds_to_time(int(data['time_in_seconds']))

                    #     pass
                    # valid timing, add

                    message_count += 1
                    yield data

                log('debug', 'Total number of messages: {}'.format(message_count))

            elif not is_live:
                # no more actions to process in a chat replay
                break
            else:
                # otherwise, is live, so keep trying
                log('debug', 'No actions to process.')

            # assume there are no more chat continuations
            no_continuation = True

            # parse the continuation information
            for cont in info.get('continuations') or []:

                continuation_key = try_get_first_key(cont)
                continuation_info = cont[continuation_key]

                if continuation_key in self._KNOWN_CHAT_CONTINUATIONS:

                    # set new chat continuation
                    # overwrite if there is continuation data
                    continuation = continuation_info.get('continuation')

                    # there is a chat continuation
                    no_continuation = False

                elif continuation_key in self._KNOWN_SEEK_CONTINUATIONS:
                    pass
                    # ignore these continuations
                else:
                    self.debug_log(params,
                                   'Unknown continuation: {}'.format(
                                       continuation_key),
                                   cont
                                   )

                # sometimes continuation contains timeout info
                sleep_duration = continuation_info.get('timeoutMs')
                # and not actions:# and not force_no_timeout:
                if sleep_duration and sleep_duration > 0:
                    # if there is timeout info, there were no actions and the user
                    # has not chosen to force no timeouts, then sleep.
                    # This is useful for streams with varying number of messages
                    # being sent per second. Timeouts help prevent 429 errors
                    # (caused by too many requests)

                    log('debug', 'Sleeping for {}ms.'.format(sleep_duration))
                    # print('time_until_timeout',timeout.time_until_timeout())
                    interruptable_sleep(sleep_duration / 1000)

            if no_continuation:  # no continuation, end
                break

            if first_time:
                first_time = False

    def get_chat_by_video_id(self, video_id, params):
        """ Get chat messages for a YouTube video, given its ID. """

        initial_info = self._get_initial_video_info(video_id)

        title = initial_info.get('title')
        duration = initial_info.get('duration')
        start_time = initial_info.get('start_time')
        is_live = initial_info.get('is_live')

        return Chat(
            self._get_chat_messages(initial_info, params),
            title=title,
            duration=duration,
            is_live=is_live,
            start_time=start_time
        )

    def get_chat(self,
                 **kwargs
                 ):

        # get video id
        url = kwargs.get('url')
        match = re.search(self._VALID_URL, url)

        if match:
            video_id = match.group('id')
            if video_id:  # normal youtube video
                return self.get_chat_by_video_id(match.group('id'), kwargs)

        #     else:  # TODO add profile, etc.
        #         pass
        # else:
        #     pass
            # Raise unsupported URL type
