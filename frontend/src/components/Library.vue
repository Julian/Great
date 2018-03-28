<template>
  <div class="uk-container" id="app">
    <table class="uk-table">
      <caption>Library</caption>
      <thead>
        <tr>
          <th>Artist</th>
          <th>Album</th>
          <th>Rating</th>
        </tr>
      </thead>

      <tbody v-for="album in albums" :key="album.id">
        <tr>
          <td>{{ album.artist.name }}</td>
          <td>{{ album.name }}</td>
          <td>
            <span v-for="n in album.rating" :key="n" uk-icon="icon: star"></span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script>
import Client from '@/great';

export default {
  name: 'Library',
  data() {
    return {
      albums: [],
    };
  },
  async created() {
    this.albums = new Client().library();
  },
};
</script>
