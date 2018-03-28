<template>
  <div class="uk-container" id="app">
    <table class="uk-table">
      <caption>Radar</caption>
      <thead>
        <tr>
          <th>Artist</th>
          <th>Album</th>
        </tr>
      </thead>

      <tbody v-for="album in albums" :key="album.id">
        <tr>
          <td>{{ album.artist.name }}</td>
          <td>{{ album.name }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script>
import Client from '@/great';

export default {
  name: 'Radar',
  data() {
    return {
      albums: [],
    };
  },
  async created() {
    this.albums = new Client().radar();
  },
};
</script>
