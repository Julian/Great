<template>
  <div class="uk-container" id="app">
    <button class="uk-align-right uk-button uk-button-primary uk-button-large">
      Add
    </button>

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
import axios from 'axios';

export default {
  name: 'Tracked',
  data() {
    return {
      artists: [],
    };
  },
  async created() {
    const response = await axios.get('/api/music/artists/tracked');
    this.artists = response.data;
  },
};
</script>
