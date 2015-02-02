"use strict";


great.Artist = Backbone.Model.extend({
});


great.ArtistsCollection = Backbone.PageableCollection.extend({
    model: great.Artist,
    comparator: "name",
    url: "/great/music/artists/",
    mode: "client",
});
