"use strict";


great.Artist = Backbone.Model.extend({
});


great.ArtistsCollection = Backbone.Collection.extend({
    model: great.Artist,
    comparator: "name",
    url: "/great/music/artists/?fields=mbid",
});
