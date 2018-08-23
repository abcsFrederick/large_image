#!/usr/bin/env python
# -*- coding: utf-8 -*-

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
            'colormapId',
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
            'invertLabel',
            'flattenLabel',
            'bitmask',
            'name',
            'opacity',
            'threshold',
            'overlayItemId',
            'offset',
            'colormapId',
        )
        self.exposeFields(AccessType.READ, fields)

        events.bind('model.item.remove', 'colormap', self._onColormapRemove)
        events.bind('model.item.remove', 'large_image', self._onItemRemove)

    def _onColormapRemove(self, event):
         self.update({'colormapId': event.item['_id']},
                     {'$unset': {'colormapId': ""}})

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
