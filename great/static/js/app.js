"use strict";
const vm = new Vue({
  el: '#app',
  data: {
    albums: [
      {name: "Something", artist: {name: "Someone"}},
      {name: "Another Thing", artist: {name: "Same One"}},
      {name: "A Third Thing", artist: {name: "A Different One"}},
    ],
  },
});
