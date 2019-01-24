import _ from 'underscore';

import { restRequest } from 'girder/rest';
import events from 'girder/events';
import FileListWidget from 'girder/views/widgets/FileListWidget';
import { wrap } from 'girder/utilities/PluginUtils';
import { AccessType } from 'girder/constants';

import LargeImageWidget from './largeImageWidget';

import largeImageFileAction from '../templates/largeImage_fileAction.pug';
import '../stylesheets/fileList.styl';

wrap(FileListWidget, 'initialize', function (initialize, settings) {
    this.largeImage = settings.largeImage;
    initialize.call(this, settings);
});

wrap(FileListWidget, 'render', function (render) {
    render.call(this);
    if (!this.parentItem || !this.parentItem.get('_id')) {
        return this;
    }
    if (this.parentItem.getAccessLevel() < AccessType.WRITE) {
        return this;
    }
    var largeImage = this.parentItem.get('largeImage');
    var files = this.collection.toArray();
    _.each(files, (file) => {
        var actions = this.$('.g-file-list-link[cid="' + file.cid + '"]')
            .closest('.g-file-list-entry').children('.g-file-actions-container');
        if (!actions.length) {
            return;
        }
        var fileAction = largeImageFileAction({
            file: file, largeImage: largeImage});
        if (fileAction) {
            actions.prepend(fileAction);
            if (actions.has('.g-large-image-remove').length) {
                file.on('g:deleted', () => {
                    this.parentItem.unset('largeImage');
                    this.parentItem.fetch();
                });
            }
        }
    });
    this.$('.g-large-image-remove').on('click', () => {
        restRequest({
            type: 'DELETE',
            url: 'item/' + this.parentItem.id + '/tiles',
            error: null
        }).done(() => {
            this.parentItem.unset('largeImage');
            this.parentItem.fetch();
        });
    });
    this.$('.g-large-image-create').on('click', (e) => {
        var cid = $(e.currentTarget).parent().attr('file-cid');
        this.largeImageDialog(cid);
    });

    if (!this.fileEdit && !this.upload && this.largeImage) {
        this.largeImageDialog(this.largeImage);
        this.largeImage = false;
    }

    return this;
});

FileListWidget.prototype.largeImageDialog = function (cid) {
    this.largeImageWidget = new LargeImageWidget({
        el: $('#g-dialog-container'),
        item: this.parentItem,
        file: this.collection.get(cid),
        parentView: this
    }).off('l:submitted', null, this).on('l:created', function () {
        this.render();
    }, this);
    this.largeImageWidget.render();
};
