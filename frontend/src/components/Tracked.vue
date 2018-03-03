<template>
  <div class="uk-container" id="app">
    <button
      class="uk-align-right uk-button uk-button-primary uk-button-large"
      uk-toggle="target: #add-tracked-artist"
      type="button">
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

    <div id="add-tracked-artist" class="uk-modal-full uk-modal" uk-modal>
      <div class="uk-modal-dialog uk-flex uk-flex-center uk-flex-middle" uk-height-viewport>
        <button class="uk-modal-close-full" type="button" uk-close></button>
        <form class="uk-search uk-search-large">
          <input
          class="uk-search-input uk-text-center"
          type="Artist"
          placeholder="Add Artist..."
          autofocus>
        </form>
      </div>
    </div>
  </div>
</template>

<script>
import Client from '@/great';

export default {
  name: 'Tracked',
  data() {
    return {
      artists: [],
    };
  },
  async created() {
    const client = new Client();
    this.artists = await client.tracked();
  },
};
</script>
