"use strict";


great.ArtistsListView = Backbone.View.extend({

    tagName: "ul",
    id: "artists",

    render: function () {
        this.$el.empty();
        _.each(this.model.models, function (artist) {
            var artistView = new great.ArtistView({model : artist})
            this.$el.append(artistView.render().el);
        }, this);
        return this;
    },
});

great.ArtistView = Backbone.View.extend({

    tagName: "li",

    render: function () {
        this.$el.html(this.template(this.model.attributes));
        return this;
    },
});
