"use strict";


great.ArtistsListView = Backbone.View.extend({

    tagName: "div",
    id: "artists",

    render: function () {
        this.$el.empty();

        var columns = [
            {name: "name", cell: "string", editable: false},
            {name: "rating", cell: "number"},
            {name: "mbid", cell: "string", editable: false, sortable: false}
        ];
        var grid = new Backgrid.Grid({
            columns: columns,
            collection: this.model
        });
        var paginator = new Backgrid.Extension.Paginator({
            collection: this.model
        });

        this.$el.append(grid.render().$el);
        this.$el.append(paginator.render().$el);

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
