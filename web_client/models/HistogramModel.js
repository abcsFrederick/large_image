import Model from 'girder/models/Model';

import { restRequest } from 'girder/rest';

var HistogramModel = Model.extend({
    defaults: {
        hist: [],
        binEdges: [],
        bins: null,
        label: null
    },

    fetch: function (opts) {
        this.set('loading', true);
        var restOpts = {
            url: `item/${this.id}/tiles/histogram`
        }
        var keys = ['fileId', 'bins', 'label'];
        var params = {};
        _.each(keys, (key) => {
            if (this.get(key) != null) {
                params[key] = this.get(key);
            }
        });
        if (_.size(params)) {
            restOpts.url += '?' + $.param(params);
        }
        opts = opts || {};
        if (opts.ignoreError) {
            restOpts.error = null;
        }
        if (opts.data) {
            restOpts.data = opts.data;
        }
        return restRequest(restOpts).done((resp) => {
            this.set('loading', false, {silent: true});
            this.set(resp);
            this.trigger('g:fetched');
        }).fail((err) => {
            if (err.status == 404) {
                /*
                restOpts.method = 'POST';
                restRequest(restOpts).done((resp) => {
                    this.set(resp);
                    this.trigger('g:fetched');
                }).fail((err) => {
                    this.set('loading', false);
                    this.trigger('g:error', err);
                });
                */
            } else {
                this.set('loading', false);
                this.trigger('g:error', err);
            }
        });
    }
});

export default HistogramModel;
