#coding: utf-8
import xmpp
import time
import sqlite3
import datetime as dt
import re


class NoteStorage():
    def __init__(self, db_file='notes.sqlite3'):
        self.dbconn = sqlite3.connect(db_file)
        self.dbcursor = self.dbconn.cursor()
        if len(self.dbcursor.execute("select * from sqlite_master").fetchall()) < 1:
            self.DbInit(db_file)

    def DbInit(self, db_file):
        print 'Db Init'
        self.dbcursor.executescript("""
        CREATE TABLE "notes" (
        "id" INTEGER PRIMARY KEY AUTOINCREMENT,
        "date" INTEGER,
        "jid" TEXT,
        "text" TEXT
        );
        CREATE INDEX "jid" on notes (jid ASC);
        """)

    def add_note(self, jid, text):
        self.dbcursor.execute("INSERT INTO notes (date,jid,text) VALUES (?, ?, ?)",
                            (int(time.time()),
                            jid.getNode() + '@' + jid.getDomain(),
                            text.strip()))
        self.dbconn.commit()
        return self.dbcursor.lastrowid

    def humandate(self, date):
        date = dt.datetime.fromtimestamp(date)
        now = dt.datetime.now()
        delta = now - date
        if delta.days == 0:
            return date.strftime('%H:%M:%S')
        else:
            return date.strftime('%d.%m.%y %H:%M')

    def list_note(self, jid, args):
        print jid.getNode()
        try:
            if args[0] == u'all':
                limit = 500
        except IndexError:
            limit = 15
        self.dbcursor.execute("SELECT id,date,text FROM notes WHERE jid=? ORDER BY date DESC LIMIT ?",
                              (jid.getNode() + '@' + jid.getDomain(),
                               limit))
        res = self.dbcursor.fetchall()
        ret = '\n'
        for r in res:
            ret += u"<b>[%s]</b> {%s} %s\n" % (r[0], self.humandate(r[1]),
                                   r[2][0:80].replace('\n', ' '))
        if len(res) == limit:
            ret += u"<em>for more items: !ls all</em>"
        return ret

    def view_note(self, jid, args):
        try:
            id = args[0]
        except IndexError:
            return u"введите id заметки (например !v 25)"
        self.dbcursor.execute("SELECT date,text FROM notes WHERE jid=? AND id=?",
                              (jid.getNode() + '@' + jid.getDomain(), id))
        res = self.dbcursor.fetchone()
        try:
            return u"\n<b>{%s}</b>\n%s" % (self.humandate(res[0]), res[1])
        except:
            return u"Error!"

    def remove_note(self, jid, args):
        try:
            id = args[0]
        except IndexError:
            return u"введите id заметки для удаления (например !r 25)"
        count_deleted = self.dbcursor.execute("DELETE FROM notes WHERE jid=? AND id=?",
                              (jid.getNode() + '@' + jid.getDomain(), id)).rowcount
        if count_deleted > 0:
            return u"удалено!"
        else:
            return u"ничего не удалено!"

    def remove_all_notes(self, jid, args):
        try:
            if args[0] == 'all!':
                count_deleted = self.dbcursor.execute("DELETE FROM notes WHERE jid=?",
                                                      (jid.getNode() + '@' + jid.getDomain(), )).rowcount
                return u"удалено %s записей к чертям" % (count_deleted)
            else:
                return u"чтобы удалить все наберите !remove all!"
        except IndexError:
            return u"чтобы удалить все наберите !remove all!"


class bot(NoteStorage):
    def __init__(self, account):
        NoteStorage.__init__(self)
        self.account = account
        self.ping_interval = 60
        self.last_ping_time = time.time()
        self.prev_ping_res = {'status': False}

    def connect(self):
        jid = xmpp.JID(self.account['jid'])
        user, server, password = jid.getNode(), jid.getDomain(), self.account['pwd']
        self.conn = xmpp.Client(server, debug=['always'])
        conres = self.conn.connect()
        authres = self.conn.auth(user, password)
        self.conn.sendInitPresence(requestRoster=1)
        self.reghandlers()
        self.prev_ping_res = {'status': True}
        msg_pr = xmpp.protocol.Presence()
        msg_pr.setStatus('type !help for help')
        msg_pr.setPriority(1)
        self.conn.send(msg_pr)
        self.bot_loop()

    def disconnect(self):
        self.conn.disconnect()

    def reconnect(self):
        while True:
            try:
                print 'trying'
                self.connect()
            except Exception as e:
                print 'Error:', e
                time.sleep(5)
            else:
                print 'success!'
                break

    def reghandlers(self):
        self.conn.RegisterHandler('message', self.inmsg)
        self.conn.RegisterHandler('iq', self.iqHandler)
        self.conn.RegisterHandler('presence', self.presenceHandler)

    def presenceHandler(self, conn, msg):
        jid = msg.getFrom()
        if msg.getType() == 'subscribe':
            self.conn.Roster.Authorize(jid)
            self.conn.Roster.Subscribe(jid)
            msg_req = xmpp.protocol.Presence(typ='subscribe')
            msg_req.setTo(jid)
            self.conn.send(msg_req)
            self.msg_send(jid, 'Welcome!')
        elif msg.getType() == 'unsubscribe':
            self.conn.Roster.Unauthorize(jid)
            self.conn.Roster.Unsubscribe(jid)
        elif msg.getType() == 'subscribed':
            msg_pr = xmpp.protocol.Presence()
            msg_pr.setStatus('type !help for help')
            msg_pr.setPriority(1)
            self.conn.send(msg_pr)

    def inmsg(self, conn, msg):
        if msg.getType() == 'chat':
            jid = msg.getFrom()
            text = msg.getBody()
            self.msg_dispatcher(jid, text)

    def msg_dispatcher(self, jid, text):
        text = text.strip()
        if text[0:1] == "!":
            self.command_dispatcher(jid, text[1:])
        else:
            idnote = self.add_note(jid, text)
            self.msg_send(jid=jid, text=u'Ваша заметка сохранена под номером <b>%s</b>' % (idnote))

    def msg_send(self, jid, text):
        #self.conn.send(xmpp.protocol.Message(jid, text))
        text += u"\n\n<em>чтобы получить справку наберите !help</em>"
        text_plain = re.sub(r'<[^>]+>', '', text)
        msg = xmpp.protocol.Message(body=text_plain)
        if text_plain != text:
            html = xmpp.Node('html', {'xmlns':
                'http://jabber.org/protocol/xhtml-im'})
            try:
                html.addChild(node=xmpp.simplexml.XML2Node(
                    "<body xmlns='http://www.w3.org/1999/xhtml'>"
                    + text.replace('\n', '<br/>').encode('utf-8') + "</body>"))
                msg.addChild(node=html)
            except Exception as e:
                print e
                msg = xmpp.protocol.Message(body=text_plain)
        msg.setTo(jid)
        self.conn.send(msg)

    def command_dispatcher(self, jid, cmd):
        cmdlist = cmd.split()
        try:
            res = getattr(self, 'cmd_' + cmdlist[0].encode('utf8'))(jid, cmdlist[1:])
        except AttributeError as e:
            print e
            self.msg_send(jid=jid, text=u'Неизвестная команда: %s' % (cmdlist[0]))

    def cmd_ls(self, *args, **kwargs):
        res = self.list_note(args[0], args[1])
        self.msg_send(args[0], res)

    def cmd_v(self, *args, **kwargs):
        res = self.view_note(args[0], args[1])
        self.msg_send(args[0], res)

    def cmd_r(self, *args, **kwargs):
        res = self.remove_note(args[0], args[1])
        self.msg_send(args[0], res)

    def cmd_remove(self, *args, **kwargs):
        res = self.remove_all_notes(args[0], args[1])
        self.msg_send(args[0], res)

    def cmd_help(self, *args, **kwargs):
        msg_help = u"""
чтобы быстро добавить заметку, просто пришлите ее этому боту и он сохранит её
=== Доступные команды ===
<b>!help</b> - эта справка
<b>!ls</b> - список 15 последних заметок
<b>!ls all</b> - список всех заметок (на самом деле только 500 последних)
<b>!v 25</b> - вывести полностью текст заметки 25
<b>!r 25</b> - удалить заметку 25
<b>!remove all!</b> - удалить вообще все заметки (осторожно, дополнительно ничего не спросит)
source: https://github.com/AyumuKasuga/notebot
"""
        self.msg_send(args[0], msg_help)

    def iqHandler(self, conn, iq_node):
        #print iq_node.getID()
        #print dir(iq_node)
        if iq_node.attrs['type'] == u'result':
            self.prev_ping_res['status'] = True

    def bot_loop(self):
        while True:
            try:
                self.conn.Process(1)
            except KeyboardInterrupt:
                self.disconnect()
                print 'bye!'
                break
            self.ping()

    def ping(self):
        if time.time() - self.ping_interval > self.last_ping_time:
            self.last_ping_time = time.time()
            iq = xmpp.Iq(typ='get')
            iq.addChild('ping', namespace='urn:xmpp:ping')
            self.conn.send(iq)
            if not self.prev_ping_res['status']:
                self.reconnect()
            self.prev_ping_res = {'id': iq.getID(), 'status': False}





