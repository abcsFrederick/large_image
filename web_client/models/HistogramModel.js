import Model from 'girder/models/Model';

import { restRequest } from 'girder/rest';

var HistogramModel = Model.extend({
    defaults: {
        hist: [],
        binEdges: [],
        bins: null,
        label: null,
        loading: false,
        bitmask: false
    },

    save: function () {
        var restOpts = {
            url: `item/${this.id}/tiles/histogram`,
            method: 'POST',
            data: {},
            error: null // don't do default error behavior (validation may fail)
        }
        _.each(this.keys(), function (key) {
            var value = this.get(key);
            if (!_.isObject(value)) {
                restOpts.data[key] = value;
            }
        }, this);

        return restRequest(restOpts).done((resp) => {
            this.set(resp);
            this.trigger('g:saved');
        }).fail((err) => {
            this.trigger('g:error', err);
        });
    },

    fetch: function (opts) {
        this.set('loading', true, {silent: true});
        var restOpts = {
            url: `item/${this.id}/tiles/histogram`
        }
        var keys = ['fileId', 'bins', 'label', 'bitmask'];
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
            this.set('loading', false, {silent: true});
            this.trigger('g:error', err);
        });
    }
});

export default HistogramModel;
