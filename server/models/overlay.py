#!/usr/bin/env python
# -*- coding: utf-8 -*-

##############################################################################
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
##############################################################################

from girder import events
from girder.constants import AccessType, SortDir
from girder.exceptions import AccessException, ValidationException
from girder.models.model_base import AccessControlledModel

class Overlay(AccessControlledModel):
    def initialize(self):
        self.name = 'overlay'
        self.ensureIndices([
            'itemId',
            'creatorId',
            'index',
            'name',
            'overlayItemId',
        ])

        fields = (
            '_id',
            'creatorId',
            'description',
            'displayed',
            'index',
            'position',
            'itemId',
            'label',
            'name',
            'opacity',
            'overlayItemId',
        )
        self.exposeFields(AccessType.READ, fields)

        events.bind('model.item.remove', 'large_image', self._onItemRemove)

    def _onItemRemove(self, event):
        item = event.info
        for overlay in self.find({'itemId': item['_id']}):
            self.remove(overlay)
        for overlay in self.find({'overlayItemId': item['_id']}):
            self.remove(overlay)

    def _getMaxIndex(self, itemId, creatorId):
        query = {
            'itemId': itemId,
            'creatorId': creatorId,
        }
        for overlay in self.find(query, sort=[('index', SortDir.DESCENDING)],
                                        fields=['index']):
            return overlay['index']
        return -1

    def createOverlay(self, user, **doc):
        self.setUserAccess(doc, user=user, level=AccessType.ADMIN,
                           save=False)
        doc['index'] = self._getMaxIndex(doc['itemId'], doc['creatorId']) + 1
        return self.save(doc)

    def updateOverlay(self, doc, update):
        doc.update(update)
        self.save(doc)

    def validate(self, doc):
        if doc.get('itemId') is None:
            raise ValidationException('Overlay must have a parent item ID')
        if doc.get('creatorId') is None:
            raise ValidationException('Overlay must have a creator ID')
        if doc.get('index') is None:
            raise ValidationException('Overlay must have an index')
        if doc.get('overlayItemId') is None:
            raise ValidationException('Overlay must have an overlay item ID')
        if doc.get('name') is None:
            raise ValidationException('Overlay must have a name')
        return doc
