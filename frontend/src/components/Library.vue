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
          <td>{{ album.rating }}</td>
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
        { name: 'Something', artist: { name: 'Someone' }, rating: 5},
        { name: 'Another Thing', artist: { name: 'Same One' }, rating: 3},
        {
          name: 'A Third Thing',
          artist: { name: 'A Different One' },
          rating: 5
        },
      ],
    };
  },
};
</script>
