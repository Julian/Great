<template>
  <div class="uk-container">
    <button
      class="uk-align-right uk-button uk-button-primary uk-button-large"
      uk-toggle="target: #add-tracked-artist"
      type="button">
      Add
    </button>

    <div id="add-tracked-artist" class="uk-modal-full uk-modal" uk-modal>
      <artist-search></artist-search>
    </div>

    <table class="uk-table">
      <caption>Tracked</caption>
      <tbody v-for="artist in artists" :key="artist.id">
        <tr>
          <td>{{ artist.name }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script>
import Client from '@/great';

import ArtistSearch from '@/components/ArtistSearch';

export default {
  name: 'Tracked',
  components: { ArtistSearch },
  data() {
    return {
      artists: [],
    };
  },
  async created() {
    const artists = await new Client().tracked();
    this.artists = artists.sort((one, two) =>
      one.name.localeCompare(two.name));
  },
};
</script>
