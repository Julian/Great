"use strict";


var StarFormatter = {
    fromRaw: function (rawValue, model) { return "★".repeat(rawValue) },
    toRaw: function (formattedValue, model) { return formattedValue.length },
}


great.ArtistsListView = Backbone.View.extend({

    tagName: "div",
    id: "artists",

    render: function () {
        this.$el.empty();

        var columns = [
            {name: "name", cell: "string", editable: false},
            {
                name: "rating",
                cell: "integer",
                formatter: StarFormatter,
                editable: false
            },
        ];
        var grid = new Backgrid.Grid({
            columns: columns,
            collection: this.model
        });
        var filter = new Backgrid.Extension.ClientSideFilter({
            collection: this.model,
            fields: ["name"]
        });
        var paginator = new Backgrid.Extension.Paginator({
            collection: this.model
        });

        this.$el.append(filter.render().$el);
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
