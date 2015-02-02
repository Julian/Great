"use strict";


var great = {
    views: {},
    models: {},

    loadTemplates: function (views) {
        var requests = [];

        $.each(views, function(index, view) {
            var templateURL = "/templates/" + view + ".html"
            var promise = Promise.resolve($.get(templateURL)).then(
                function (data) {
                    great[view].prototype.template = _.template(data);
                }
            );
            requests.push(promise);
        });

        return Promise.all(requests);
    },
};


great.Router = Backbone.Router.extend({

    routes: {
        "": "home",
    },

    initialize: function() {
        this.$content = $("#content");
    },

    home: function () {
        great.artists = new great.ArtistsCollection();

        var self = this;
        Promise.resolve(
            great.artists.fetch(
                {dataType: "json", data: {fields: "mbid,rating"}}
            )
        ).then(
            function () {
                great.artistsListView = new great.ArtistsListView(
                    {model: great.artists}
                );
                great.artistsListView.render()
                self.$content.html(great.artistsListView.el);
            }
        );
    }

});


$(document).on("ready", function () {
    var views = ["ArtistsListView", "ArtistView"];
    great.loadTemplates(views).then(
        function () {
            great.router = new great.Router();
            Backbone.history.start();
        },
        function (error) { 
            console.error(error);
        }
    )
});
