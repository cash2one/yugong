#!/usr/bin/env python
# encoding: utf-8


"""
@author: william
@contact: 1342247033@qq.com
@site: http://www.xiaolewei.com
@file: toutiao.py
@time: 02/03/2018 23:25
"""

import requests
import json
import os
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
import base64
import random
from zhon.hanzi import punctuation

from entities import Article
from core import config, db
from core import logger,  mail, cache
from utils import browser, uploader
import time


class ToutiaoOperator(object):

    _login_url = 'https://sso.toutiao.com/login/?service=https://mp.toutiao.com/sso_confirm/?redirect_url=/'
    _graphic_url = 'https://mp.toutiao.com/profile_v3/graphic'
    _publish_url = 'https://mp.toutiao.com/profile_v3/graphic/publish/?pgc_id=%s'

    def __init__(self):
        self._browser = browser.get()
        self._wait = WebDriverWait(self._browser, 10)
        self._login()
        pass

    def __del__(self):
        self._browser.close()

    def _wait_for_recognize_captcha(self, encoded_captcha):
        etcd = db.get_etcd_client(config.get('app.db.etcd'))
        key = 'yugong/toutiao/login/captcha/%d' % random.randint(0, 999999)
        img_name = str(random.random())[2:] + '.gif'
        local_file = config.APP_PATH + '/storage/cache/' + img_name
        with open(local_file, 'ab') as f:
            f.write(base64.b64decode(encoded_captcha.split('base64,')[1]))
        qiniu_url = uploader.upload(config.APP_PATH + '/storage/cache/' + img_name)
        logger.notice('=================Waiting for recognize=================')
        logger.notice('[%s] [%s]' % (key, qiniu_url))
        link_url = config.get('app.toutiao.notify_url') % (qiniu_url, key)
        mail.send(config.get('app.toutiao.notify_receiver'),
                'Yugong-captcha', "<h2>%s</h2><img src=\"%s\" /><a href=\"%s\">填写</a>" % (key, qiniu_url, link_url))
        rtn = etcd.watch(key)
        print(rtn)
        etcd.delete(key)
        return rtn.value

        # while not res:
        #     logger.info('waiting for recognize captcha')
        #     time.sleep(10)
        #     res = cache.get('captcha-%s' % key)
        # print(type(res))
        # if isinstance(res, bytes):
        #     res = bytes.decode(res)

        #res = input('Please input the captcha')
        #cache.delete('captcha-%s' % key)
        logger.info('Get recognized captcha [%s]' % res)
        return str(res)

    def _wait_for_phone_num(self, phone):
        key = 'yugong/toutiao/login/phone/%s' % phone
        etcd = db.get_etcd_client(config.get('app.db.etcd'))
        rtn = etcd.watch(key)
        return rtn.value

    def _login(self):
        '''
        Login with cookie if cookie file exists, otherwise login with account and password, and
        save cookie to cookie file
        Login with phone number has not been handled
        :return:
        '''
        self._browser.get(self._login_url)
        cached_cookie = self._get_saved_cookie()
        if cached_cookie and len(cached_cookie) > 0:
            cookies = json.loads(cached_cookie)
            for cookie in cookies:
                self._browser.add_cookie(cookie)
            self._browser.get(self._graphic_url)
            time.sleep(5)
        # cookie has expired, remove it
        if 'login' in self._browser.current_url:
            self._browser.get(self._login_url)
            logger.notice('Login toutiao with cached cookie failed')
        else:
            logger.info('Login toutiao with cookie successfully')

        # cookie_file = (config.APP_PATH + '/storage/cache/toutiao/%s.txt') % config.get('app.toutiao.account')
        # print(cookie_file)
        # print(os.path.exists(cookie_file))
        # if os.path.exists(cookie_file):
        #     logger.info('Login toutiao with cookie file')
        #     with open(cookie_file) as f:
        #         cookies = json.loads(f.read())
        #         for cookie in cookies:
        #             self._browser.add_cookie(cookie)
        #         self._browser.get(self._graphic_url)
        #         time.sleep(5)
        #         # cookie has expired, remove it
        #         if 'login' in self._browser.current_url:
        #             self._browser.get(self._login_url)
        #             logger.notice('Login toutiao with cookie file failed')
        #             os.remove(cookie_file)
        #         else:
        #             logger.info('Login toutiao with cookie successfully')
        #             return

        while 'login' in self._browser.current_url:
            try:
                err = self._browser.find_element_by_class_name('error-msg')
                tips = err.text.strip('\t\r\n ')
                if '手机验证码' in tips:
                    phone_num = config.get('app.toutiao.phone')
                    logger.notice('Verify account by phone number')
                    phone = self._wait.until(EC.presence_of_element_located((By.ID, 'mobile')))
                    code = self._wait.until(EC.presence_of_element_located((By.ID, 'code')))
                    send_btn = self._wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'code-btn')))
                    submitBtn = self._wait.until(EC.presence_of_element_located((By.NAME, 'submitBtn')))
                    phone.send_keys(phone_num)
                    send_btn.click()
                    received_code = self._wait_for_phone_num(phone_num)
                    code.send_keys(received_code)
                    submitBtn.click()
                    self._update_cookie()
                    break
            except NoSuchElementException as e:
                pass
            logger.info('Try to login toutiao [%s]' % self._browser.current_url)
            name = self._wait.until(EC.presence_of_element_located((By.ID, 'account')))
            pwd = self._wait.until(EC.presence_of_element_located((By.ID, 'password')))
            captcha = self._wait.until(EC.presence_of_element_located((By.ID, 'captcha')))
            captcha_img = self._wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'captcha')))
            submit = self._wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'action-btn')))
            recognized_captcha = self._wait_for_recognize_captcha(captcha_img.get_attribute('src'))
            name.clear()
            pwd.clear()
            captcha.clear()
            name.send_keys(config.get('app.toutiao.account'))
            pwd.send_keys(config.get('app.toutiao.password'))
            captcha.send_keys(recognized_captcha)
            submit.submit()
            time.sleep(3)
            err = self._browser.find_element_by_class_name('error-msg')
            print(err)
        self._update_cookie()
        logger.info('login toutiao successfully')

    def _update_cookie(self):
        key = 'yugong.toutiao.cookie.%s' % config.get('app.toutiao.account')
        cookie_file = (config.APP_PATH + '/storage/cache/toutiao/%s.txt') % config.get('app.toutiao.account')
        if not os.path.exists(os.path.split(cookie_file)[0]):
            os.makedirs(os.path.split(cookie_file)[0])
        json_cookie = json.dumps(self._browser.get_cookies())
        cache.put(key, json_cookie)
        with open(cookie_file, 'w+') as f:
            f.write(json_cookie)

    def _get_saved_cookie(self):
        key = 'yugong.toutiao.cookie.%s' % config.get('app.toutiao.account')
        return cache.get(key)

    def _get_action_xpath(self):
        if 'graphic/publish' not in self._browser.current_url:
            return None
        return {
            'cover': {
                'single': '//div[@class="article-cover"]//label[1]//input',
                'triple': '//div[@class="article-cover"]//label[2]//input',
                'auto': '//div[@class="article-cover"]//label[3]//input',
            },
            'ad': {
                'toutiao': '//div[@class="form-wrap"]/div[2]//label[1]//input',
                'self': '//div[@class="form-wrap"]/div[2]//label[2]//input',
                'none': '//div[@class="form-wrap"]/div[2]//label[3]//input',
            },
            'act': {
                # TODO
            },
            'action': {
                'publish': '//div[contains(@class, "figure-footer")]/div[@class="edit-input"]/div[1]'
            }
        }


    def publish(self, articles):
        for article_id in articles:
            try:
                self._browser.get(self._publish_url % article_id)
                time.sleep(5)
                xpaths = self._get_action_xpath()
                self._browser.execute_script("window.scrollTo(0,document.body.scrollHeight)")
                ad_toutiao = self._wait.until(EC.presence_of_element_located((By.XPATH, xpaths['ad']['toutiao']))),
                cover_auto = self._wait.until(EC.presence_of_element_located((By.XPATH, xpaths['cover']['auto']))),
                publish_btn = self._wait.until(EC.presence_of_element_located((By.XPATH, xpaths['action']['publish']))),
                logger.debug('Captcha button: ', ad_toutiao, cover_auto, publish_btn)
                ad_toutiao[0].click()
                cover_auto[0].click()
                publish_btn[0].click()
                try:
                    body = self._wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'dialog-body')))
                    if '手机动态验证' in body.getText():
                        logger.info('Need to verify phone number')
                except Exception as e:
                    logger.error(e)
                    pass

            except Exception as e:
                logger.error('Publish failed')
                logger.error(e)
            finally:
                time.sleep(10)

    @logger.log('Operate')
    def schedule(self, num=1):
        '''
        Get all the article in drafted status, and publish them
        :return:
        '''
        self._browser.get(url=self._graphic_url)
        time.sleep(10)
        self._browser.execute_script("window.scrollTo(0,document.body.scrollHeight)")
        time.sleep(6)
        soup = BeautifulSoup(self._browser.page_source)
        articles = []
        self._wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'article-card')))
        for card in soup.find_all('div', class_='article-card'):
            try:
                title_div = card.find('div', class_='master-title')
                title = title_div.get_text().strip('\t\r\n ')
                logger.info('Schedule is handling [%s]' % title)
                status = card.find('span', class_='article-status-label').get_text().strip('\n\r\t ')
                if status != '草稿':
                    logger.info('Schedule skip [%s] due to [%s]' % (title, status))
                    continue
                url = title_div.a['href']
                idx = url.rfind('=')
                articles.append(url[idx+1:])
            except Exception as e:
                logger.info('Schedule article failed')
                logger.error(e)
        logger.info('Find [%d] articles are in ready' % len(articles))
        self.publish(articles[-num:])
        self._update_cookie()


class Toutiao:
    _url = 'https://mp.toutiao.com/open/new_article_post/'
    _headers = {
        'Content-Type': 'application/x-www-form-urlencoded; UTF-8'
    }

    def __init__(self):
        self._access_token = config.get('app.toutiao.access_token')
        self._client_key = config.get('app.toutiao.client_key')
        pass

    def transformer(self, article: Article):
        '''
        :param article:
        :return:
        purify href of img tag
        '''
        soup = BeautifulSoup(article.html)

        # purify image
        for img in soup.find_all('img'):
            try:
                if 'src' in img.attrs:
                    img['src'] = uploader.upload(img['src'])
            except Exception as e:
                logger.error(e)
                continue

        # remove link
        for a in soup.find_all('a'):
            try:
                if 'href' in a.attrs:
                    del a['href']
            except Exception as e:
                logger.error(e)
                continue

        # control length of title 5-30
        # 一个汉字算一个长度，2个字母算一个长度
        alpha_num = 1
        word_num = 0
        for x in range(len(article.title)):
            if alpha_num / 2 + word_num >= 28:
                article.title = article.title[:x]
            if article.title[x] in punctuation or (u'/u4e00' <= article.title[x] <= u'/u9fa5'):
                word_num += 1
            else:
                alpha_num += 1
        if alpha_num / 2 + word_num < 5:
            article.title = '技术专栏-' + article.title

        # append summarize
        summ = ''
        if article.abstract_str:
            summ = '<h1>内容导读</h1><blockquote><p>%s</p></blockquote>' % str(article.abstract_str)
        article.html = summ + str(soup)

    def publish(self, article):
        try:
            self.transformer(article)
            resp = requests.post('%s?access_token=%s&client_key=%s' % (self._url, self._access_token, self._client_key),
                                 {
                                     'title': article.title,
                                     'content': article.html,
                                     'save': 0
                                 }, headers=self._headers, timeout=20)
            res = json.loads(resp.text)
            if res and 'message' in res and res['message'] == 'success':
                logger.info('Publish article [%s] success' % article.title)
            else:
                logger.error('Publish error:')
                logger.error('response: [%s]' % res['data'])
                logger.error('title: [%s]' % article.title)

        except Exception as e:
            logger.error('Toutiao publish [%s] error' % article.title)
            logger.error(e)
            pass
