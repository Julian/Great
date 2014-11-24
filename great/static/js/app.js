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
        great.artistsView = new great.ArtistsView();
        great.artistsView.render();
        this.$content.html(great.artistsView.el);
    }

});


$(document).on("ready", function () {
    var views = ["ArtistsView"];
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
