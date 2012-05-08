#coding: utf-8
from notebot import bot

#введите сюда логин и пароль от jabber аккаунта к которому будет конектиться этот бот
b = bot(account={'jid': 'notebot@xmpp.ru', 'pwd': 'password'})
b.connect()
