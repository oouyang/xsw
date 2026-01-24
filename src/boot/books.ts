import { boot } from 'quasar/wrappers';
import { useBookStore } from 'src/stores/books';

export default boot(() => {
  const book = useBookStore();
  book.load();
});
