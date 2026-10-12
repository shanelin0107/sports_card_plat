import type { Holding } from './types';

type Graded = Pick<Holding, 'grade_value' | 'grade_label'>;

/** "BGS 9.5" -> "BGS"; holdings saved without a company count as PSA. */
export const graderOf = (h: Graded) => (h.grade_value && h.grade_label.includes(' ') ? h.grade_label.split(' ')[0] : 'PSA');

/** Grade as the API takes it: raw, psa10, bgs9.5 … */
export const gradeParam = (h: Graded) => (h.grade_value ? `${graderOf(h).toLowerCase()}${h.grade_value}` : 'raw');
