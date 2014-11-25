"use strict";


great.Artist = Backbone.Model.extend({
    urlRoot: "/great/music/artists/",
});


great.ArtistsCollection = Backbone.Collection.extend({
    model: great.Artist,
    url: "/great/music/artists/",
});
