/**
 * Time axis. Switched off in this version: every record is treated as current.
 *
 * It is kept so a later version can show how things changed over time. Records may carry a
 * `since` year (the year a product was recognised, a technique was listed, and so on). When the
 * axis is on, a record is shown once the chosen year reaches its `since` year; records without
 * one are always shown.
 *
 * To turn it on: set CONFIG.features.timeline = true in js/app.js, or add ?timeline=1 to the
 * address while developing.
 */
(function () {
  'use strict';

  class Timeline {
    /**
     * @param {{enabled: boolean, element: HTMLElement, label: string, onChange: function(number): void}} options
     */
    constructor(options) {
      this.enabled = Boolean(options.enabled);
      this.element = options.element;
      this.label = options.label || ''; // the words beside the slider, in the page's language
      this.onChange = options.onChange || function () {};
      this.min = null;
      this.max = null;
      this.year = null;
    }

    /** Work out the span of years from the records' `since` values. */
    setRecords(records) {
      const years = [];
      for (const r of records) {
        if (Number.isFinite(r.since)) years.push(r.since);
      }
      if (!years.length) return;
      this.min = Math.min.apply(null, years);
      this.max = Math.max.apply(null, years);
      if (this.year === null) this.year = this.max;
      this.render();
    }

    /** Should this record be shown at the chosen year? Always true while the axis is off. */
    accepts(record) {
      if (!this.enabled || this.year === null) return true;
      return !(Number.isFinite(record.since) && record.since > this.year);
    }

    setYear(year) {
      if (this.min === null) return;
      const next = Math.max(this.min, Math.min(this.max, Math.round(year)));
      if (next === this.year) return;
      this.year = next;
      this.render();
      this.onChange(next);
    }

    render() {
      if (!this.element) return;
      this.element.hidden = !this.enabled || this.min === null;
      if (this.element.hidden) return;
      if (!this.slider) {
        const label = document.createElement('label');
        label.className = 'timeline-label';
        label.htmlFor = 'timeline-slider';
        label.textContent = this.label;
        this.slider = document.createElement('input');
        this.slider.type = 'range';
        this.slider.id = 'timeline-slider';
        this.slider.step = '1';
        this.slider.addEventListener('input', () => this.setYear(Number(this.slider.value)));
        this.readout = document.createElement('output');
        this.readout.className = 'timeline-year';
        this.readout.htmlFor = 'timeline-slider';
        this.element.append(label, this.slider, this.readout);
      }
      this.slider.min = String(this.min);
      this.slider.max = String(this.max);
      this.slider.value = String(this.year);
      this.readout.textContent = String(this.year);
    }
  }

  window.FoodMapTimeline = Timeline;
})();
