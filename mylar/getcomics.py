# -*- coding: utf-8 -*-
# This file is part of Mylar.
#
# Mylar is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Mylar is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Mylar.  If not, see <http://www.gnu.org/licenses/>.


import requests
import urllib.parse
import os
import sys
import traceback
import errno
import re
import time
import datetime
from bs4 import BeautifulSoup
import cfscrape
import zipfile
import mylar
from mylar import db, logger, helpers


class GC(object):
    def __init__(self, query=None, issueid=None, comicid=None, oneoff=False):

        self.valreturn = []

        self.url = 'https://getcomics.info'

        self.query = query  #{'comicname', 'issue', year'}

        self.comicid = comicid

        self.issueid = issueid

        self.oneoff = oneoff

        self.local_filename = os.path.join(mylar.CONFIG.CACHE_DIR, "getcomics.html")

        self.search_format = ['"%s #%s (%s)"', '%s #%s (%s)', '%s #%s', '%s %s']

        self.headers = {
            'Accept-encoding': 'gzip',
            'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:40.0) Gecko/20100101 Firefox/40.1',
            'Referer': 'https://getcomics.info/',
        }

    def search(self):
        results = {}
        resultset = []
        try:
            with cfscrape.create_scraper() as s:
                try:
                    cf_cookievalue, cf_user_agent = s.get_tokens(
                        self.url, headers=self.headers
                   )
                except Exception as e:
                    cf_cookievalue = None
                    cf_user_agent = None

                for sf in self.search_format:
                    sf_issue = self.query['issue']
                    if any([self.query['issue'] == 'None', self.query['issue'] is None]):
                        sf_issue = None
                    if sf.count('%s') == 3:
                        if sf == self.search_format[1]:
                            #don't modify the specific query that is around quotation marks.
                            if any([r'/' in self.query['comicname'], r':' in self.query['comicname']]):
                                self.query['comicname'] = re.sub(r'[/|:]', ' ', self.query['comicname'])
                                self.query['comicname'] = re.sub(r'\s+', ' ', self.query['comicname'])
                        if sf_issue is None:
                            splits = sf.split(' ')
                            splits.pop(1)
                            queryline = ' '.join(splits) % (self.query['comicname'], self.query['year'])
                        else:
                            queryline = sf % (self.query['comicname'], sf_issue, self.query['year'])
                    else:
                        if sf_issue is None:
                            splits = sf.split(' ')
                            splits.pop(1)
                            queryline = ' '.join(splits) % (self.query['comicname'])
                        else:
                            queryline = sf % (self.query['comicname'], sf_issue)

                    logger.fdebug('[DDL-QUERY] Query set to: %s' % queryline)

                    t = s.get(
                        self.url + '/',
                        params={'s': queryline},
                        verify=True,
                        cookies=cf_cookievalue,
                        headers=self.headers,
                        stream=True,
                        timeout=30,
                    )

                    with open(self.local_filename, 'wb') as f:
                        for chunk in t.iter_content(chunk_size=1024):
                            if chunk:  # filter out keep-alive new chunks
                                f.write(chunk)
                                f.flush()

                    for x in self.search_results()['entries']:
                        bb = next((item for item in resultset if item['link'] == x['link']), None)
                        try:
                            if 'Weekly' not in self.query['comicname'] and 'Weekly' in x['title']:
                                continue
                            elif bb is None:
                                resultset.append(x)
                        except:
                            resultset.append(x)
                        else:
                            continue

                    if len(resultset) > 1:
                        break
                    time.sleep(2)

        except requests.exceptions.Timeout as e:
            logger.warn(
                'Timeout occured fetching data from DDL: %s' % e
            )
            return 'no results'
        except requests.exceptions.ConnectionError as e:
            logger.warn(
                '[WARNING] Connection refused to DDL site, stopped by a small tank.'
                ' Error returned as : %s' % e
            )
            if any(
                [
                    errno.ETIMEDOUT,
                    errno.ECONNREFUSED,
                    errno.EHOSTDOWN,
                    errno.EHOSTUNREACH,
                ]
            ):
                helpers.disable_provider('DDL', 'Connection Refused.')
            return 'no results'
        except Exception as err:
            logger.warn(
                '[WARNING] Unable to scrape remote site, stopped by a small tank.'
                ' Error returned as : %s' % err
            )
            if 'Unable to identify Cloudflare IUAM' in str(err):
                helpers.disable_provider(
                    'DDL', 'Unable to identify Cloudflare IUAM Javascript on website'
                )

            # since we're capturing exceptions here, searches from the search module
            # won't get capture. So we need to do this so they get tracked.
            exc_type, exc_value, exc_tb = sys.exc_info()
            filename, line_num, func_name, err_text = traceback.extract_tb(
                exc_tb
            )[-1]
            tracebackline = traceback.format_exc()

            except_line = {
                'exc_type': exc_type,
                'exc_value': exc_value,
                'exc_tb': exc_tb,
                'filename': filename,
                'line_num': line_num,
                'func_name': func_name,
                'err': str(err),
                'err_text': err_text,
                'traceback': tracebackline,
                'comicname': None,
                'issuenumber': None,
                'seriesyear': None,
                'issueid': self.issueid,
                'comicid': self.comicid,
                'mode': None,
                'booktype': None,
            }

            helpers.log_that_exception(except_line)

            return 'no results'
        else:
            results['entries'] = resultset
            return results

    def loadsite(self, id, link):
        title = os.path.join(mylar.CONFIG.CACHE_DIR, 'getcomics-' + id)
        with cfscrape.create_scraper() as s:
            try:
                self.cf_cookievalue, cf_user_agent = s.get_tokens(
                    link, headers=self.headers
                )
            except Exception as e:
                self.cf_cookievalue = None
                self.cf_user_agent = None

            t = s.get(
                link,
                verify=True,
                cookies=self.cf_cookievalue,
                headers=self.headers,
                stream=True,
                timeout=30,
            )

            with open(title + '.html', 'wb') as f:
                for chunk in t.iter_content(chunk_size=1024):
                    if chunk:  # filter out keep-alive new chunks
                        f.write(chunk)
                        f.flush()

    def search_results(self):
        results = {}
        resultlist = []
        soup = BeautifulSoup(open(self.local_filename, encoding='utf-8'), 'html.parser')

        resultline = soup.find("span", {"class": "cover-article-count"}).get_text(
            strip=True
        )
        logger.info('There are %s results' % re.sub('Articles', '', resultline).strip())

        for f in soup.findAll("article"):
            id = f['id']
            lk = f.find('a')
            link = lk['href']
            titlefind = f.find("h1", {"class": "post-title"})
            title = titlefind.get_text(strip=True)
            title = re.sub('\u2013', '-', title).strip()
            filename = title
            issues = None
            pack = False
            # see if it's a pack type
            issfind_st = title.find('#')
            issfind_en = title.find('-', issfind_st)
            if issfind_en != -1:
                if all([title[issfind_en + 1] == ' ', title[issfind_en + 2].isdigit()]):
                    iss_en = title.find(' ', issfind_en + 2)
                    if iss_en != -1:
                        issues = title[issfind_st + 1 : iss_en]
                        pack = True
                if title[issfind_en + 1].isdigit():
                    iss_en = title.find(' ', issfind_en + 1)
                    if iss_en != -1:
                        issues = title[issfind_st + 1 : iss_en]
                        pack = True

            # to handle packs that are denoted without a # sign being present.
            # if there's a dash, check to see if both sides of the dash are numeric.
            if pack is False and title.find('-') != -1:
                issfind_en = title.find('-')
                if all(
                       [
                           title[issfind_en + 1] == ' ',
                           title[issfind_en + 2].isdigit(),
                       ]
                ) and all(
                       [
                           title[issfind_en -1] == ' ',
                       ]
                ):
                    spaces = [m.start() for m in re.finditer(' ', title)]
                    dashfind = title.find('-')
                    space_beforedash = title.find(' ', dashfind - 1)
                    space_afterdash = title.find(' ', dashfind + 1)
                    if not title[space_afterdash+1].isdigit():
                        pass
                    else:
                        iss_end = title.find(' ', space_afterdash + 1)
                        if iss_end == -1:
                            iss_end = len(title)
                        set_sp = None
                        for sp in spaces:
                            if sp < space_beforedash:
                                prior_sp = sp
                            else:
                                set_sp = prior_sp
                                break
                        if title[set_sp:space_beforedash].strip().isdigit():
                            issues = title[set_sp:iss_end].strip()
                            pack = True

            # if it's a pack - remove the issue-range and the possible issue years
            # (cause it most likely will span) and pass thru as separate items
            if pack is True:
                brackets = re.findall("\(.*?\)", title)
                for b in brackets:
                    if issues in b:
                        title = re.sub(b, '', title).strip()
                        break
                if not brackets:
                    title = re.sub(issues, '', title).strip()
                # kill any brackets in the issue line here.
                issues = re.sub(r'[\(|\)|\[|\]]', '', issues).strip()
                if title.endswith('#'):
                    title = title[:-1].strip()
            else:
                if any(
                    [
                        'Marvel Week+' in title,
                        'INDIE Week+' in title,
                        'Image Week' in title,
                        'DC Week+' in title,
                    ]
                ):
                    continue

            option_find = f.find("p", {"style": "text-align: center;"})
            i = 0
            if option_find is None:
                continue
            else:
                while i <= 2 and option_find is not None:
                    option_find = option_find.findNext(text=True)
                    if 'Year' in option_find:
                        year = option_find.findNext(text=True)
                        year = re.sub(r'\|', '', year).strip()
                        if pack is True and '-' in year:
                            title = re.sub(r'\(' + year + r'\)', '', title).strip()
                    else:
                        size = option_find.findNext(text=True)
                        if all(
                            [
                                re.sub(':', '', size).strip() != 'Size',
                                len(re.sub(r'[^0-9]', '', size).strip()) > 0,
                            ]
                        ):
                            if all(
                                      [
                                          '-' in size,
                                          re.sub(r'[^0-9]', '', size).strip() == '',
                                      ]
                            ):
                                size = None
                            if 'MB' in size:
                                size = re.sub('MB', 'M', size).strip()
                            if 'GB' in size:
                                size = re.sub('GB', 'G', size).strip()
                            if '//' in size:
                                nwsize = size.find('//')
                                size = re.sub(r'\[', '', size[:nwsize]).strip()
                            elif '/' in size:
                                nwsize = size.find('/')
                                size = re.sub(r'\[', '', size[:nwsize]).strip()
                            if '-' in size:
                                size = None
                        else:
                            size = '0M'
                    i += 1
            dateline = f.find('time')
            datefull = dateline['datetime']
            datestamp = time.mktime(time.strptime(datefull, "%Y-%m-%d"))
            resultlist.append(
                {
                    "title": title,
                    "pubdate": datetime.datetime.fromtimestamp(
                        float(datestamp)
                    ).strftime('%a, %d %b %Y %H:%M:%S'),
                    "filename": filename,
                    "size": re.sub(' ', '', size).strip(),
                    "pack": pack,
                    "issues": issues,
                    "link": link,
                    "year": year,
                    "id": re.sub('post-', '', id).strip(),
                    "site": 'DDL',
                }
            )

            logger.fdebug('%s [%s]' % (title, size))

        results['entries'] = resultlist
        return results

    def parse_downloadresults(self, id, mainlink, comicinfo=None):
        try:
            booktype = comicinfo[0]['booktype']
        except Exception:
            booktype = None
        myDB = db.DBConnection()
        series = None
        year = None
        size = None
        title = os.path.join(mylar.CONFIG.CACHE_DIR, 'getcomics-' + id)
        soup = BeautifulSoup(open(title + '.html', encoding='utf-8'), 'html.parser')
        orig_find = soup.find("p", {"style": "text-align: center;"})
        i = 0
        option_find = orig_find
        possible_more = None
        while True:  # i <= 10:
            prev_option = option_find
            option_find = option_find.findNext(text=True)
            if i == 0 and series is None:
                series = option_find
            elif 'Year' in option_find:
                year = option_find.findNext(text=True)
                year = re.sub(r'\|', '', year).strip()
            else:
                if 'Size' in prev_option:
                    size = option_find  # .findNext(text=True)
                    possible_more = orig_find.next_sibling
                    break
            i += 1

        logger.fdebug(
            'Now downloading: %s [%s] / %s ... this can take a while'
            ' (go get some take-out)...' % (series, year, size)
        )

        link = None
        for f in soup.findAll("div", {"class": "aio-pulse"}):
            lk = f.find('a')
            if lk['title'] == 'Download Now':
                link = {
                    "series": series,
                    "site": lk['title'],
                    "year": year,
                    "issues": None,
                    "size": size,
                    "link": lk['href'],
                }

                break  # get the first link just to test

        links = []

        if link is None and possible_more.name == 'ul':
            try:
                bb = possible_more.findAll('li')
            except Exception:
                pass
            else:
                for x in bb:
                    linkline = x.find('a')
                    try:
                        tmp = linkline['href']
                    except Exception:
                        continue
                    if tmp:
                        if any(
                            [
                                'run.php' in linkline['href'],
                                'go.php' in linkline['href'],
                                'comicfiles.ru' in linkline['href'],
                            ]
                        ):
                            volume = x.findNext(text=True)
                            if '\u2013' in volume:
                                volume = re.sub(r'\u2013', '-', volume)
                            # volume label contains series, issue(s), year(s), and size
                            series_st = volume.find('(')
                            issues_st = volume.find('#')
                            series = volume[:series_st]
                            if any([issues_st == -1, series_st == -1]):
                                issues = None
                            else:
                                series = volume[:issues_st].strip()
                                issues = volume[issues_st + 1 : series_st].strip()
                            year_end = volume.find(')', series_st + 1)
                            year = re.sub(
                                r'[\(\)]', '', volume[series_st + 1 : year_end]
                            ).strip()
                            size_end = volume.find(')', year_end + 1)
                            size = re.sub(
                                r'[\(\)]', '', volume[year_end + 1 : size_end]
                            ).strip()
                            linked = linkline['href']
                            site = linkline.findNext(text=True)
                            if site == 'Main Server':
                                links.append(
                                    {
                                        "series": series,
                                        "site": site,
                                        "year": year,
                                        "issues": issues,
                                        "size": size,
                                        "link": linked,
                                    }
                                )
        else:
            if booktype != 'TPB':
                logger.fdebug('TPB links detected, but booktype set to %s' % booktype)
            else:
                check_extras = soup.findAll("h3")
                for sb in check_extras:
                    header = sb.findNext(text=True)
                    if header == 'TPBs' and bookype == 'TPB':
                        nxt = sb.next_sibling
                        if nxt.name == 'ul':
                            bb = nxt.findAll('li')
                            for x in bb:
                                volume = x.findNext(text=True)
                                if '\u2013' in volume:
                                    volume = re.sub(r'\u2013', '-', volume)
                                series_st = volume.find('(')
                                issues_st = volume.find('#')
                                series = volume[:issues_st].strip()
                                issues = volume[issues_st:series_st].strip()
                                year_end = volume.find(')', series_st + 1)
                                year = re.sub(
                                    r'[\(\)\|]', '', volume[series_st + 1 : year_end]
                                ).strip()
                                size_end = volume.find(')', year_end + 1)
                                size = re.sub(
                                    r'[\(\)\|]', '', volume[year_end + 1 : size_end]
                                ).strip()
                                linkline = x.find('a')
                                linked = linkline['href']
                                site = linkline.findNext(text=True)
                                links.append(
                                    {
                                        "series": series,
                                        "volume": volume,
                                        "site": site,
                                        "year": year,
                                        "issues": issues,
                                        "size": size,
                                        "link": linked,
                                    }
                                )

        if all([link is None, len(links) == 0]):
            logger.warn(
                'Unable to retrieve any valid immediate download links.'
                ' They might not exist.'
            )
            return {'success': False}
        if all([link is not None, len(links) == 0]):
            logger.info(
                'Only one item discovered, changing queue length to accomodate: %s [%s]'
                % (link, type(link))
            )
            links = [link]
        elif len(links) > 0:
            if link is not None:
                links.append(link)
                logger.fdebug(
                    '[DDL-QUEUE] Making sure we download the original item in addition'
                    ' to the extra packs.'
                )
            if len(links) > 1:
                logger.fdebug(
                    '[DDL-QUEUER] This pack has been broken up into %s separate packs -'
                    ' queueing each in sequence for your enjoyment.' % len(links)
                )
        cnt = 1
        for x in links:
            if len(links) == 1:
                mod_id = id
            else:
                mod_id = id + '-' + str(cnt)
            # logger.fdebug('[%s] %s (%s) %s [%s][%s]'
            #     % (x['site'], x['series'], x['year'], x['issues'],
            #     x['size'],  x['link'])
            #     )

            ctrlval = {'id': mod_id}
            vals = {
                'series': x['series'],
                'year': x['year'],
                'size': x['size'],
                'issues': x['issues'],
                'issueid': self.issueid,
                'comicid': self.comicid,
                'link': x['link'],
                'mainlink': mainlink,
                'updated_date': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
                'status': 'Queued',
            }
            myDB.upsert('ddl_info', vals, ctrlval)

            mylar.DDL_QUEUE.put(
                {
                    'link': x['link'],
                    'mainlink': mainlink,
                    'series': x['series'],
                    'year': x['year'],
                    'size': x['size'],
                    'comicid': self.comicid,
                    'issueid': self.issueid,
                    'oneoff': self.oneoff,
                    'id': mod_id,
                    'resume': None,
                }
            )
            cnt += 1

        return {'success': True}

    def downloadit(self, id, link, mainlink, resume=None):
        # logger.info('[%s] %s -- mainlink: %s' % (id, link, mainlink))
        if mylar.DDL_LOCK is True:
            logger.fdebug(
                '[DDL] Another item is currently downloading via DDL. Only one item can'
                ' be downloaded at a time using DDL. Patience.'
            )
            return
        else:
            mylar.DDL_LOCK = True

        myDB = db.DBConnection()
        filename = None
        try:
            with cfscrape.create_scraper() as s:
                if resume is not None:
                    logger.info(
                        '[DDL-RESUME] Attempting to resume from: %s bytes' % resume
                    )
                    self.headers['Range'] = 'bytes=%d-' % resume
                try:
                    cf_cookievalue, cf_user_agent = s.get_tokens(
                        mainlink, headers=self.headers, timeout=30
                    )
                except Exception as e:
                    cf_cookievalue = None
                    cf_user_agent = None

                t = s.get(
                    link,
                    verify=True,
                    cookies=cf_cookievalue,
                    headers=self.headers,
                    stream=True,
                    timeout=30,
                )

                filename = os.path.basename(
                    urllib.parse.unquote(t.url)
                )  # .decode('utf-8'))
                if 'GetComics.INFO' in filename:
                    filename = re.sub('GetComics.INFO', '', filename, re.I).strip()

                try:
                    remote_filesize = int(t.headers['Content-length'])
                    logger.fdebug('remote filesize: %s' % remote_filesize)
                except Exception as e:
                    if 'run.php-urls' not in link:
                        link = re.sub('run.php-url=', 'run.php-urls', link)
                        link = re.sub('go.php-url=', 'run.php-urls', link)
                        t = s.get(
                            link,
                            verify=True,
                            cookies=cf_cookievalue,
                            headers=self.headers,
                            stream=True,
                            timeout=30,
                        )
                        filename = os.path.basename(
                            urllib.parse.unquote(t.url)
                        )  # .decode('utf-8'))
                        if 'GetComics.INFO' in filename:
                            filename = re.sub(
                                'GetComics.INFO', '', filename, re.I
                            ).strip()
                        try:
                            remote_filesize = int(t.headers['Content-length'])
                            logger.fdebug('remote filesize: %s' % remote_filesize)
                        except Exception as e:
                            logger.warn(
                                '[WARNING] Unable to retrieve remote file size - this'
                                ' is usually due to the page being behind a different'
                                ' click-bait/ad page. Error returned as : %s' % e
                            )
                            logger.warn(
                                '[WARNING] Considering this particular download as'
                                ' invalid and will ignore this result.'
                            )
                            remote_filesize = 0
                            mylar.DDL_LOCK = False
                            return {
                                "success": False,
                                "filename": filename,
                                "path": None,
                            }

                    else:
                        logger.warn(
                            '[WARNING] Unable to retrieve remote file size - this is'
                            ' usually due to the page being behind a different'
                            ' click-bait/ad page. Error returned as : %s' % e
                        )
                        logger.warn(
                            '[WARNING] Considering this particular download as invalid'
                            ' and will ignore this result.'
                        )
                        remote_filesize = 0
                        mylar.DDL_LOCK = False
                        return {"success": False, "filename": filename, "path": None}

                # write the filename to the db for tracking purposes...
                myDB.upsert(
                    'ddl_info',
                    {'filename': filename, 'remote_filesize': remote_filesize},
                    {'id': id},
                )

                if mylar.CONFIG.DDL_LOCATION is not None and not os.path.isdir(
                    mylar.CONFIG.DDL_LOCATION
                ):
                    checkdirectory = mylar.filechecker.validateAndCreateDirectory(
                        mylar.CONFIG.DDL_LOCATION, True
                    )
                    if not checkdirectory:
                        logger.warn(
                            '[ABORTING] Error trying to validate/create DDL download'
                            ' directory: %s.' % mylar.CONFIG.DDL_LOCATION
                        )
                        return {"success": False, "filename": filename, "path": None}

                path = os.path.join(mylar.CONFIG.DDL_LOCATION, filename)

                # if t.headers.get('content-encoding') == 'gzip':
                #    buf = StringIO(t.content)
                #    f = gzip.GzipFile(fileobj=buf)

                if resume is not None:
                    with open(path, 'ab') as f:
                        for chunk in t.iter_content(chunk_size=1024):
                            if chunk:
                                f.write(chunk)
                                f.flush()

                else:
                    with open(path, 'wb') as f:
                        for chunk in t.iter_content(chunk_size=1024):
                            if chunk:
                                f.write(chunk)
                                f.flush()

        except Exception as e:
            logger.error('[ERROR] %s' % e)
            mylar.DDL_LOCK = False
            return {"success": False, "filename": filename, "path": None}

        else:
            mylar.DDL_LOCK = False
            if os.path.isfile(path):
                if path.endswith('.zip'):
                    new_path = os.path.join(
                        mylar.CONFIG.DDL_LOCATION, re.sub('.zip', '', filename).strip()
                    )
                    logger.info(
                        'Zip file detected.'
                        ' Unzipping into new modified path location: %s' % new_path
                    )
                    try:
                        zip_f = zipfile.ZipFile(path, 'r')
                        zip_f.extractall(new_path)
                        zip_f.close()
                    except Exception as e:
                        logger.warn(
                            '[ERROR: %s] Unable to extract zip file: %s' % (e, new_path)
                        )
                        return {"success": False, "filename": filename, "path": None}
                    else:
                        try:
                            os.remove(path)
                        except Exception as e:
                            logger.warn(
                                '[ERROR: %s] Unable to remove zip file from %s after'
                                ' extraction.' % (e, path)
                            )
                        filename = None
                else:
                    new_path = path
                return {"success": True, "filename": filename, "path": new_path}

    def issue_list(self, pack):
        # packlist = [x.strip() for x in pack.split(',)]
        packlist = pack.replace('+', ' ').replace(',', ' ').split()
        print(packlist)
        plist = []
        pack_issues = []
        for pl in packlist:
            if '-' in pl:
                plist.append(
                    list(
                        range(int(pl[: pl.find('-')]), int(pl[pl.find('-') + 1 :]) + 1)
                    )
                )
            else:
                if 'TPBs' not in pl:
                    plist.append(int(pl))
                else:
                    plist.append('TPBs')

        for pi in plist:
            if type(pi) == list:
                for x in pi:
                    pack_issues.append(x)
            else:
                pack_issues.append(pi)

        pack_issues.sort()
        print("pack_issues: %s" % pack_issues)


# if __name__ == '__main__':
#    ab = GC(sys.argv[1]) #'justice league aquaman') #sys.argv[0])
#    #c = ab.search()
#    b = ab.loadsite('test', sys.argv[2])
#    c = ab.parse_downloadresults('test', '60MB')
#    #c = ab.issue_list(sys.argv[2])
