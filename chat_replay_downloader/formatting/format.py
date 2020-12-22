import re
import datetime
import os
import json

# from ..utils import (
#     microseconds_to_timestamp
# )

# TODO remove and use utils


def microseconds_to_timestamp(microseconds, format='%Y-%m-%d %H:%M:%S'):
    """Convert unix time to human-readable timestamp."""
    return datetime.datetime.fromtimestamp(microseconds//1000000).strftime(format)


class ItemFormatter:

    _INDEX_REGEX = r'(?<!\\){(.+?)(?<!\\)}'

# 'always_show': True (default False)

    def __init__(self, path=os.path.join(os.path.dirname(os.path.realpath(__file__)), 'custom_formats.json')):
        with open(path) as custom_formats:
            self.format_file = json.load(custom_formats)

    def replace(self, result, item, format_object):
        #print(format_object.keys(), item)
        # print()
        # split by | not enclosed in []
        # split = result.split('|') #re.split(, result.group(2))
        split = result.group(1).split('|')
        # print(split)
        for index in split:
            value = item.get(index)
            formatting_info = format_object.get(index)
            if value:  # found and non-empty, will return
                if formatting_info:
                    pass
                    prefix = formatting_info.get('prefix') or ''

                    suffix = formatting_info.get('suffix') or ''

                    # Apply formatting
                    formatting = formatting_info.get('format')
                    if formatting:
                        if index == 'timestamp':
                            value = microseconds_to_timestamp(
                                value, formatting)
                        elif index == '':
                            pass

                    # Apply separator
                    separator = formatting_info.get('separator')
                    if separator:
                        if index == 'author_badges':
                            value = separator.join(
                                map(lambda key: key.get('title'), value))
                        elif isinstance(value, (tuple, list)):
                            value = separator.join(value)
                        else:
                            pass
                            # incorrect
                    # print(formatting)

                    return '{}{}{}'.format(prefix, value, suffix)

                else:
                    return str(value)
                # print(value)

                # return ''  # value

            #

        return ''  # no match, return empty

    def format(self, item, format_name='default', format_object=None):
        if format_object is None:
            format_object = self.format_file.get(format_name)

        if isinstance(format_object, list):
            format_object = next((x for x in format_object if item.get(
                'message_type') in x.get('matching')), None)

        if not format_object:
            return  # raise no format given

        #f = format_object.get()
        template = format_object.get('template')
        keys = format_object.get('keys')

        substitution = re.sub(self._INDEX_REGEX, lambda result: self.replace(
            result, item, keys), template)
        empty_substitution = re.sub(self._INDEX_REGEX, '', template)
        #print(substitution, empty_substitution)
        # returns (new, num_modifications)
        if substitution != empty_substitution:  # some substitution made
            return substitution
        else:
            return None


item1 = {
    "action_type": "text_message",
    "author_badges": [
        {
            "badge_id": "5d9f2208-5dd8-11e7-8513-2ff4adfae661",
            "click_action": "subscribe_to_channel",
            "click_url": "",
            "description": "1-Month Subscriber",
            "icons": [
                {
                        "height": 18,
                        "id": "18x18",
                        "url": "https://static-cdn.jtvnw.net/badges/v1/5d9f2208-5dd8-11e7-8513-2ff4adfae661/1",
                        "width": 18
                },
                {
                    "height": 36,
                    "id": "36x36",
                    "url": "https://static-cdn.jtvnw.net/badges/v1/5d9f2208-5dd8-11e7-8513-2ff4adfae661/2",
                    "width": 36
                },
                {
                    "height": 72,
                    "id": "72x72",
                    "url": "https://static-cdn.jtvnw.net/badges/v1/5d9f2208-5dd8-11e7-8513-2ff4adfae661/3",
                    "width": 72
                }
            ],
            "months": 1,
            "title": "1-Month Subscriber",
            "type": "subscriber",
            "version": 0
        }
    ],
    "author_display_name": "pr0faka",
    "author_id": "545470622",
    "author_name": "pr0faka",
    "channel_id": "151283108",
    "colour": "#008000",
    "is_moderator": False,
    "message": "people born in 1988 have a bad time picking user names",
    "message_id": "ac48cdd8-af9b-4d4a-be5a-7eaaacbd212a",
    "message_type": "text_message",
    "timestamp": 1608220470845000
}
item2 = {
    "action_type": "add_chat_item",
    "author_badges": [
        {
            "icons": [
                {
                    "height": 16,
                    "id": "16x16",
                    "url": "https://yt3.ggpht.com/7Y0B8yW1lfXCmMR5JR5pmney6UxJPBdL--4QgVqVKlPcMr-i0IF2Y74ghx3lhIkDzuybfRTQWA=s16-c-k",
                    "width": 16
                },
                {
                    "height": 32,
                    "id": "32x32",
                    "url": "https://yt3.ggpht.com/7Y0B8yW1lfXCmMR5JR5pmney6UxJPBdL--4QgVqVKlPcMr-i0IF2Y74ghx3lhIkDzuybfRTQWA=s32-c-k",
                    "width": 32
                },
                {
                    "id": "source",
                    "url": "https://yt3.ggpht.com/7Y0B8yW1lfXCmMR5JR5pmney6UxJPBdL--4QgVqVKlPcMr-i0IF2Y74ghx3lhIkDzuybfRTQWA"
                }
            ],
            "title": "Member (2 months)"
        }
    ],
    "author_id": "UCjGX7N9LQNwTYvXFGyxwS2w",
    "author_images": [
        {
            "height": 32,
            "url": "https://yt3.ggpht.com/ytc/AAUvwnjuAJvUDBEYFogGefU7LcpeQvih0KAXamHdj35hBw=s32-c-k-c0xffffffff-no-rj-mo",
            "width": 32
        },
        {
            "height": 64,
            "url": "https://yt3.ggpht.com/ytc/AAUvwnjuAJvUDBEYFogGefU7LcpeQvih0KAXamHdj35hBw=s64-c-k-c0xffffffff-no-rj-mo",
            "width": 64
        }
    ],
    "author_name": "Sophia Sokolova",
    "message": "6 minutes :_raeHype:",
    "message_id": "CjkKGkNKeVd6SnJleS0wQ0ZiSGtnZ29kWWJ3T29nEhtDSmpCaDdIY3ktMENGUnJmVlFvZGRBOEFpdzc%3D",
    "message_type": "text_message",
    "time_in_seconds": -76,
    "time_text": "-1:16",
    "timestamp": 1607889245637404
}
# formatter = ItemFormatter()

# formatted = formatter.format(item2)
# print(formatted)