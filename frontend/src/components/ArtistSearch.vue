<template>
  <div class="uk-modal-dialog uk-flex uk-flex-center uk-flex-middle" uk-height-viewport>
    <button class="uk-modal-close-full" type="button" uk-close></button>
    <form class="uk-search uk-search-large">
      <input
      @keyup.enter="doSearch"
      v-model="artist"
      class="uk-search-input uk-text-center"
      type="Artist"
      placeholder="Add Artist..."
      autofocus>
    </form>
  </div>
</template>

<script>
import * as SpotifyWebApi from 'spotify-web-api-js';

export default {
  name: 'ArtistSearch',
  data() {
    return {
      artist: '',
    };
  },
  methods: {
    async doSearch() {
      const spotify = new SpotifyWebApi();
      await spotify.searchArtists(this.artist);
    },
  },
};
</script>
