import imaplib
#import imaplib_connect
import time
import email.message
import json
import redis
import hashlib

# starting Redis: redis-server


def test_imap_service(s_username, s_password, s_imap_url, i_debug_level):
    """
    Executes a test of basic functions against a specified IMAP service
    :rtype : str
    :param s_username: IMAP account user name
    :param s_password: IMAP account password
    :param s_imap_url: URL of IMAP service
    :param i_debug_level: Level of debug output; 0: none, 1: user+time, 2: step-level times
    :return: Success/fail message description (only returned if i_debug_level > 0)
    """
    # Declarations
    b_has_failed_check = False
    time_start = time.time()  # Start the clock
    time_last = time.time()
    timestamp = {'User': s_username, '00_StartTime': time_format(time.localtime(time_start))}

    # Connect to service
    try:
        o_imap = imaplib.IMAP4_SSL(s_imap_url)
        timestamp['010_Connect'] = ((time.time() - time_last) * 1000.0)
        time_last = time.time()
    except:  # imaplib.IMAP4.error as e:
        timestamp['Error'] = u'Unable to connect to URL: {0:s}'.format(str(s_imap_url))  # + '; ' + str(e)
        b_has_failed_check = True

    # Login to service
    if not b_has_failed_check:
        try:
            o_imap.login(s_username, s_password)
            timestamp['020_Login'] = ((time.time() - time_last) * 1000.0)
            time_last = time.time()
        except imaplib.IMAP4.error as e:
            timestamp['Error'] = 'Unable to login with user credentials; ' + str(e)
            b_has_failed_check = True

    # Select inbox
    if not b_has_failed_check:
        try:
            o_imap.select('inbox')
            timestamp['030_SelectInbox'] = ((time.time() - time_last) * 1000.0)
            time_last = time.time()
        except imaplib.IMAP4.error as e:
            timestamp['Error'] = 'Unable to select inbox; ' + str(e)
            b_has_failed_check = True

    # List objects in inbox
    if not b_has_failed_check:
        try:
            result, data = o_imap.uid('search', None, "ALL")
            timestamp['040_ListObjects'] = ((time.time() - time_last) * 1000.0)
            time_last = time.time()
        except imaplib.IMAP4.error as e:
            timestamp['Error'] = 'Unable to return inbox messages; ' + str(e)
            b_has_failed_check = True

        # Run inbox operations
        if len(data[0]) > 0:
            # Pull first message ID
            email_uid = data[0].split()[-1]

            # Fetch first message
            result, data = o_imap.uid('fetch', email_uid, '(RFC822)')
            timestamp['050_FetchMessage'] = ((time.time() - time_last) * 1000.0)
            time_last = time.time()
            raw_email = data[0][1]

            # Mark message as read
            o_imap.uid('STORE', email_uid, '+FLAGS', '(\SEEN)')
            timestamp['060_MarkRead'] = ((time.time() - time_last) * 1000.0)
            time_last = time.time()

            # EmailMessage = email.message_from_bytes(raw_email)

            # Mark message as unread
            o_imap.uid('STORE', email_uid, '-FLAGS', '(\SEEN)')
            timestamp['070_MarkUnread'] = ((time.time() - time_last) * 1000.0)
            time_last = time.time()

            # Delete "imap_mail_test" emails
            result, [msg_ids] = o_imap.search(None, 'SUBJECT','IMAP Mail Test')
            if msg_ids != '':
                msg_ids = ','.join(msg_ids.split(' '))
                result, response = o_imap.store(msg_ids, '+FLAGS', r'(\Deleted)')
                #result, response = o_imap.expunge()
            timestamp['080_DeleteMessage'] = ((time.time() - time_last) * 1000.0)

            # Create "imap_mail_test" email
            new_message = email.message.Message()
            # new_message.set.unixfrom('foobar')
            new_message['Subject'] = 'IMAP Mail Test'
            new_message['From'] = 'foobar@anywhere.com'
            new_message['To'] = s_username + '@anywhere.com'
            new_message.set_payload('IMAP mail test content\n')
            o_imap.append('INBOX', '\Flagged', imaplib.Time2Internaldate(time.time()), str(new_message))
            timestamp['090_CreateMessage'] = ((time.time() - time_last) * 1000.0)

        else:
            s_alert_message = 'WARNING: No messages in inbox\n'

        o_imap.close()
        o_imap.logout()

    time_last = time.time()

    timestamp['100_Complete'] = ((time.time() - time_last) * 1000.0)
    timestamp['110_EndTime'] = time_format(time.localtime(time_last))
    timestamp['115_TotalTime'] = ((time_last - time_start) * 1000.0)


    if b_has_failed_check:
        timestamp['Succeeded'] = 0
    else:
        timestamp['Succeeded'] = 1

    # Return JSON object
    return json.dumps(timestamp, sort_keys=True)


def time_format(o_time):
    return time.strftime("%Y-%m-%d %H:%M:%S %Z", o_time)


def get_earliest_test_results():
    """
    Fetches the test results from the earliest (first) index in the cache
    """
    o_cache = redis.StrictRedis('localhost')

    # Fetch, output all values in first index
    s_read_index = o_cache.lpop('index')

    if s_read_index != '':
        i_user_count = o_cache.llen(s_read_index)

        if i_user_count > 0:
            for iUser in range(1, i_user_count + 1):
                o_json = o_cache.lpop(s_read_index)
                print '{0}: {1}'.format(str(iUser - 1), str(o_json))
        else:
            print('ERROR: No values for run time: ' + s_read_index)
    else:
        print('ERROR: No keys in index')


def execute_imap_test(i_user_index_min, i_user_index_max,  i_debug_level):
    """
    Executes IMAP test for specified number of users
    :param i_user_index_min: Minimum index value to check against (inclusive)
    :param i_user_index_max: Maximum index value to check against (inclusive)
    :param i_debug_level: Level of debug output; 0: none, 1: user+time, 2: step-level times
    """
    s_username_template = 'a_test_user_%05d'
    s_username = ''
    s_imap_url = 'imap.anywhere.com'
    time_start = time.time()
    s_time_start = str(time_start)
    o_cache = redis.StrictRedis('localhost')

    if i_debug_level > 0:
        print('Start: ' + time_format(time.localtime(time_start)) + '\n------------------------------')

    for iUser in range(i_user_index_min, i_user_index_max + 1):
        s_username = (s_username_template % iUser)
        o_json = test_imap_service(s_username, hashlib.md5(s_username).hexdigest()[:16], s_imap_url, i_debug_level)
        o_cache.rpush(s_time_start, o_json)
        # print(s_username + ' ' + hashlib.md5(s_username).hexdigest()[:16])

    # Add key to Redis index (once complete)
    o_cache.rpush('index', s_time_start)

    get_earliest_test_results()

    if i_debug_level > 0:
        print('------------------------------\nEnd:   ' + time_format(time.localtime(time.time())))


execute_imap_test(0, 9, 1)

