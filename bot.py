import json
import os
import time
import datetime
from configparser import ConfigParser
import re
import sys
import logging
from logging.handlers import RotatingFileHandler
import traceback

from fbchat import Client, ThreadType, Message, EmojiSize, Sticker, TypingStatus, MessageReaction, ThreadColor, Mention
import asyncio

import data

#logging.basicConfig(level=logging.DEBUG)

def config(filename=sys.path[0] + '/config.ini', section='facebook credentials'):
    # create a parser 
    parser = ConfigParser()
    # read config file
    parser.read(filename)

    # get section
    creds = {}
    if parser.has_section(section):
        params = parser.items(section)
        for param in params:
            creds[param[0]] = param[1]
    elif os.environ['EMAIL']: 
        creds['email'] = os.environ['EMAIL']
        creds['password'] = os.environ['PASSWORD']
    else:
        raise Exception(
            'Section {0} not found in the {1} file'.format(section, filename))
    return creds


class HydroBot(Client):
    #def pmMe(self, txt):
    #    self.send(Message(text = txt), thread_id = client.uid, thread_type=ThreadType.USER)
    #1398444230228776 old? testing chat
    #2813871368632313 testing chat
    #1802551463181435 water chat
    async def on_message(self, author_id, message_object, thread_id, thread_type, **kwargs):
        print("meme") 
        if message_object.text is not None and (thread_id == '1802551463181435' or thread_type == ThreadType.USER):
        #if message_object.text is not None and (thread_id == '2813871368632313' or thread_type == ThreadType.USER):
            messageText = message_object.text
            ma = messageText.split() # message array

            threadinfo = await self.fetch_thread_info(thread_id)
            emoji = threadinfo[thread_id].emoji
            if ma[0].lower() == "physics":
                await process_message(self, author_id, ma, thread_id, thread_type, message_object)
            elif messageText == emoji:
                await homie_increment(self, thread_id, thread_type, author_id, message_object)
        super(HydroBot, self).on_message(author_id=author_id, message_object=message_object, thread_id=thread_id, thread_type=thread_type, **kwargs)

async def process_message(self, author_id, ma, thread_id, thread_type, message_object):
    if author_id != self.uid:
        print(ma)
        userinfo = await self.fetch_user_info(author_id)
        user = userinfo[author_id]
        name = user.name
        try:
            data.insert_homie(author_id, name)
        except:
            pass
        threadinfo = await self.fetch_thread_info(thread_id)
        emoji = threadinfo[thread_id].emoji
        if ma[1] == "help":
            txt = """
physics stats ([num] [interval]) (-v|full|verbose)- lists stats
  -> "physics stats 1 day full"
  -> "physics stats"
  -> "physics stats 1 minute"
  -> "physics stats -v"
physics add [name] [num] - add a bottle (!!no whitespace!!) and its size (give in ml)
physics remove [name] - remove your bottle called [name] (Warning, will delete all drink events made with this bottle)
physics switch [name] - switch your current bottle to the bottle with [name]
physics drink [name] - logs a single drink with bottle [name], does not change current bottle
physics rename [name] [newname] - rename a bottle
physics list - shows all of your bottles
physics decrement - remove the last drink event
{} - tap emoji to log a drink, uses your current bottle
""".format(emoji)
            await self.send(Message(text = txt), thread_id=thread_id, thread_type=thread_type)
        elif ma[1] == "add" and str.isdigit(ma[3]):
            data.insert_bottle(ma[2], ma[3], author_id)
        elif ma[1] == "remove":
            data.delete_bottle(ma[2], author_id)
        elif ma[1] == "switch":
            data.switch_bottle(ma[2], author_id)
        elif ma[1] == "rename":
            data.rename_bottle(ma[2], ma[3], author_id)
        elif ma[1] == "list":
            await get_homie_bottles(self, thread_id, thread_type, author_id)
        elif ma[1] == "decrement" or ma[1] == "dec":
            await homie_decrement(self, thread_id, thread_type, author_id, message_object)
        elif ma[1] == "increment" or ma[1] == "inc":
            await homie_increment(self, thread_id, thread_type, author_id, message_object)
        elif ma[1] == "drink":
            data.insert_drink(author_id, bottle_name=ma[2])
        elif ma[1] == "stats":
            verbose_list = ["-v", "full", "verbose", "--verbose"]
            if len(ma)>2 and ma[2] in verbose_list:
                await group_stats(self, thread_id, thread_type, verbose=True)
            elif len(ma)>3 and str.isdigit(ma[2]) and ma[3] in ["second","minute","hour","day","week","year","seconds","minutes","hours","days","weeks","years"]:
                ts = "{} {}".format(ma[2], ma[3])
                if len(ma)>4 and ma[4] in verbose_list:
                    await group_stats(self, thread_id, thread_type, time_string=ts, verbose=True)
                else:
                    await group_stats(self, thread_id, thread_type, time_string=ts, verbose=False)
            else:
                await group_stats(self, thread_id, thread_type, verbose=False)

async def send_message(self, txt, thread_id, thread_type):
    await self.send(Message(text=txt), thread_id=thread_id, thread_type=thread_type)

def add_homie(self, thread_id, thread_type, fbid, name, size):
    data.insert_homie(fbid, name)

async def homie_increment(self, thread_id, thread_type, author_id, message_object):
    data.insert_drink(author_id)
    await self.react_to_message(message_object.uid, MessageReaction.HEART)

async def homie_decrement(self, thread_id, thread_type, author_id, message_object):
    data.delete_last_drink(author_id)
    await self.react_to_message(message_object.uid, MessageReaction.HEART)

async def get_homie_bottles(self, thread_id, thread_type, fb_id):
    string = "Your Bottles:"
    selected = data.get_bottle(fb_id)
    bottles = data.get_bottle_stats(fb_id)
    bottles = sorted(filter(lambda x: x[1] != 'NULL', bottles), key=lambda x: x[3], reverse=True)
    for b in bottles:
        indic = '-' if b[0] != selected else '🍼'
        string += "\n {} {} : {}mL : {} total drinks".format(indic, b[1], b[2], b[3])
    await self.send(Message(text=string), thread_id = thread_id, thread_type=thread_type) 


def homie_stats(fb_id, time_string):
    # All the bottles registered to a person
    bottles = dict(data.get_bottle_ids(fb_id))
    
    # Every event for person within timespan but only the bottle ids
    events_as_bottle_ids = [i for (i,) in data.get_homie_events_over_time(fb_id, time_string)]

    total = 0
    sums = len(events_as_bottle_ids)
    for e in events_as_bottle_ids:
        total = total + bottles[e]
        if bottles[e] == 0:
            sums = sums-1
    return [total/1000, sums]


async def group_stats(self, thread_id, thread_type, time_string='1 day', verbose=False):
    homies = dict(data.get_homie_list())
    homie_results = []
    string = "Hydration Stats over the past {}:".format(time_string)
    for hid in homies:
        stats = homie_stats(hid, time_string)
        homie_results.append([homies[hid], stats[0], stats[1]])

    homie_results.sort(key=lambda x: (x[1]),reverse=True)
    homie_results = filter(lambda x: x[0] != 'AssumeZero Bot', homie_results)
    king_quota = 1
    for h in homie_results:
        if verbose:
            string = string + "\n - {} drank {}L (finishing {} bottles total in the past {})".format(h[0], h[1], h[2], time_string)
        else:
            if h[1] < 2.0:
                string = string + "\n 🥵 "
            elif king_quota > 0:
                string = string + "\n 👑 "
                king_quota = 0
            else:
                string = string + "\n 👍 "
            string = string + "{}: {}L".format(h[0], h[1])
    await self.send(Message(text=string), thread_id = thread_id, thread_type=thread_type) 

def startupClient(email, password):
    try:
        with open("session.txt", "r") as session:
            session_cookies = json.loads(session.read())
    except FileNotFoundError:
        session_cookies = None

    client = HydroBot()
    with open("session.txt", "w") as session:
        session.write(json.dumps(client.getSession()))
    return client

loop = asyncio.get_event_loop()


async def start():
    client=HydroBot()
    print("Logging in...")
    await client.start("sykesstudents@gmail.com", "ThisThingSucks006")
    print("Logged in")
    client.listen()


### Reving up the engines ###
#creds = config()
#print(creds)
#client = startupClient(creds['email'], creds['password'])
loop.run_until_complete(start())
loop.run_forever()
