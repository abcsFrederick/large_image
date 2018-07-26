#!/usr/bin/env python
# -*- coding: utf-8 -*-

#############################################################################
#  Copyright Kitware Inc.
#
#  Licensed under the Apache License, Version 2.0 ( the "License" );
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#############################################################################


import threading
import math
# attempt to import girder config
try:
    from girder import logprint, logger
    from girder.utility import config
except ImportError:
    import logging as logger
    logprint = logger
    config = None

try:
    from .memcache import MemCache
except ImportError:
    MemCache = None
from cachetools import LRUCache

try:
    import psutil
except ImportError:
    psutil = None


defaultConfig = {}


def getConfig(key=None, default=None):
    """
    Get the config dictionary or a value from the cache config settings.

    :param key: if None, return the config dictionary.  Otherwise, return the
        value of the key if it is set or the default value if it is not.
    :param default: a value to return if a key is requested and not set.
    :returns: either the config dictionary or the value of a key.
    """
    if config:
        curConfig = config.getConfig().get('large_image', defaultConfig)
    else:
        curConfig = defaultConfig
    if key is None:
        return curConfig
    return curConfig.get(key, default)


def setConfig(key, value):
    """
    Set a value in the cache config settings.

    :param key: the key to set.
    :param value: the value to store in the key.
    """
    curConfig = getConfig()
    if curConfig.get(key) is not value:
        curConfig[key] = value


def pickAvailableCache(sizeEach, portion=8, maxItems=None):
    """
    Given an estimated size of an item, return how many of those items would
    fit in a fixed portion of the available virtual memory.

    :param sizeEach: the expected size of an item that could be cached.
    :param portion: the inverse fraction of the memory which can be used.
    :param maxItems: if specified, the number of items is never more than this
        value.
    :return: the number of items that should be cached.  Always at least two,
        unless maxItems is less.
    """
    # Estimate usage based on (1 / portion) of the total virtual memory.
    if psutil:
        memory = psutil.virtual_memory().total
    else:
        memory = 1024 ** 3
    numItems = max(int(math.floor(memory / portion / sizeEach)), 2)
    if maxItems:
        numItems = min(numItems, maxItems)
    return numItems


class CacheFactory(object):
    logged = False

    def getCacheSize(self, numItems):
        if numItems is None:
            defaultPortion = 8 if config else 32
            try:
                portion = int(getConfig('cache_python_memory_portion', defaultPortion))
                if portion < 3:
                    portion = 3
            except ValueError:
                portion = defaultPortion
            numItems = pickAvailableCache(256**2 * 4 * 2, portion)
        return numItems

    def getCache(self, numItems=None):
        curConfig = getConfig()
        # memcached is the fallback default, if available.
        cacheBackend = curConfig.get('cache_backend', 'memcached' if config else 'python')
        if cacheBackend:
            cacheBackend = str(cacheBackend).lower()
        cache = None
        if cacheBackend == 'memcached' and MemCache and numItems is None:
            # lock needed because pylibmc(memcached client) is not threadsafe
            cacheLock = threading.Lock()

            # check if credentials and location exist for girder otherwise
            # assume location is 127.0.0.1 (localhost) with no password
            url = curConfig.get('cache_memcached_url')
            if not url:
                url = '127.0.0.1'
            memcachedUsername = curConfig.get('cache_memcached_username')
            if not memcachedUsername:
                memcachedUsername = None
            memcachedPassword = curConfig.get('cache_memcached_password')
            if not memcachedPassword:
                memcachedPassword = None
            try:
                cache = MemCache(url, memcachedUsername, memcachedPassword,
                                 mustBeAvailable=True)
            except Exception:
                logger.info('Cannot use memcached for caching.')
                cache = None
        if cache is None:  # fallback backend
            cacheBackend = 'python'
            cache = LRUCache(self.getCacheSize(numItems))
            cacheLock = threading.Lock()
        if numItems is None and not CacheFactory.logged:
            logprint.info('Using %s for large_image caching' % cacheBackend)
            CacheFactory.logged = True
        return cache, cacheLock
