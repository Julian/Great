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
export default {
  name: 'Radar',
  data() {
    return {
      albums: [
        { name: 'Something', artist: { name: 'Someone' } },
        { name: 'Another Thing', artist: { name: 'Same One' } },
        { name: 'A Third Thing', artist: { name: 'A Different One' } },
      ],
    };
  },
};
</script>
