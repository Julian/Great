<template>
  <div class="uk-container" id="app">
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
export default {
  name: 'Tracked',
  data() {
    return {
      artists: [
        { name: 'Someone' },
        { name: 'Someone Else' },
        { name: 'Someone Also Else' },
      ],
    };
  },
};
</script>
