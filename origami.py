from __future__ import division
import sublime, sublime_plugin
import time
import threading
import copy
from functools import partial

XMIN, YMIN, XMAX, YMAX = list(range(4))

try:
    # Do not import State directly to not break us in case the MaxPane.max_pane module is reloaded
    import MaxPane

except ImportError as error:
    print('Origami Error: Could not import the MaxPane package!', error)

    class MaxPane(object):

        class max_pane(object):

            class State(object):
                is_fixing_layout = False


def increment_if_greater_or_equal(x, threshold):
    if x >= threshold:
        return x+1
    return x


def decrement_if_greater(x, threshold):
    if x > threshold:
        return x-1
    return x


def pull_up_cells_after(cells, threshold):
    return [    [x0,decrement_if_greater(y0, threshold),
                x1,decrement_if_greater(y1, threshold)] for (x0,y0,x1,y1) in cells]


def push_right_cells_after(cells, threshold):
    return [    [increment_if_greater_or_equal(x0, threshold),y0,
                increment_if_greater_or_equal(x1, threshold),y1] for (x0,y0,x1,y1) in cells]


def push_down_cells_after(cells, threshold):
    return [    [x0,increment_if_greater_or_equal(y0, threshold),
                x1,increment_if_greater_or_equal(y1, threshold)] for (x0,y0,x1,y1) in cells]


def pull_left_cells_after(cells, threshold):
    return [    [decrement_if_greater(x0, threshold),y0,
                decrement_if_greater(x1, threshold),y1] for (x0,y0,x1,y1) in cells]


def opposite_direction(direction):
    opposites = {'up':'down', 'right':'left', 'down':'up', 'left':'right'}
    return opposites[direction]


def cells_adjacent_to_cell_in_direction(cells, cell, direction):
    fn = None
    if direction == 'up':
        fn = lambda orig, check: orig[YMIN] == check[YMAX]
    elif direction == 'right':
        fn = lambda orig, check: orig[XMAX] == check[XMIN]
    elif direction == 'down':
        fn = lambda orig, check: orig[YMAX] == check[YMIN]
    elif direction == 'left':
        fn = lambda orig, check: orig[XMIN] == check[XMAX]

    if fn:
        return [c for c in cells if fn(cell, c)]
    return None


def fixed_set_layout(window, layout):
    #A bug was introduced in Sublime Text 3, sometime before 3053, in that it
    #changes the active group to 0 when the layout is changed. Annoying.
    MaxPane.max_pane.State.is_fixing_layout = True
    active_group = window.active_group()
    window.run_command('set_layout', layout)

    num_groups = len(layout['cells'])
    window.focus_group(min(active_group, num_groups-1))
    MaxPane.max_pane.State.is_fixing_layout = False


def fixed_set_layout_no_focus_change(window, layout):
    window.run_command('set_layout', layout)


def is_pane_zoomed(window):
    return window.settings().get( 'original_panes_layout' )


def maximize_pane(window, fraction):

    if fraction:
        window.run_command( 'zoom_pane', { 'fraction': fraction } )

    else:
        window.run_command( 'maximize_pane' )


def unmaximize_pane(window):
    settings = window.settings()

    if settings.get( 'origami_fraction' ):
        window.run_command( 'unzoom_pane' )

    else:
        window.run_command( 'unmaximize_pane' )


def run_unzoomed(self, target_function):
    has_zoom = self.has_zoom()
    window = self.window

    if has_zoom:
        settings = window.settings()
        unmaximize_pane( window )

        def try_create(attempt):

            if attempt < 0:
                print( "Origami Error: Timed out to create the pane..." )
                return

            has_zoom = self.has_zoom()
            if has_zoom:
                sublime.set_timeout( lambda: try_create( attempt - 1 ), 100 )

            else:
                target_function()

        try_create( 15 )

    else:
        target_function()


class WithSettings:
    _settings = None

    def settings(self):
        if self._settings is None:
            self._settings = sublime.load_settings('Origami.sublime-settings')
        return self._settings


class PaneCommand(sublime_plugin.WindowCommand, WithSettings):
    """ Abstract base class for commands. """

    def layout(self):
        layout = self.window.layout()
        cells = layout['cells']
        rows = layout['rows']
        cols = layout['cols']
        return rows, cols, cells

    def get_cells(self):
        return self.layout()[2]

    def adjacent_cell(self, direction):
        cells = self.get_cells()
        current_cell = cells[self.window.active_group()]
        adjacent_cells = cells_adjacent_to_cell_in_direction(cells, current_cell, direction)
        rows, cols, _ = self.layout()

        if direction in ['left', 'right']:
            MIN, MAX, fields = YMIN, YMAX, rows
        else: #up or down
            MIN, MAX, fields = XMIN, XMAX, cols

        cell_overlap = []
        for cell in adjacent_cells:
            start = max(fields[cell[MIN]], fields[current_cell[MIN]])
            end = min(fields[cell[MAX]], fields[current_cell[MAX]])
            overlap = (end - start)# / (fields[cell[MAX]] - fields[cell[MIN]])
            cell_overlap.append(overlap)

        if len(cell_overlap) != 0:
            cell_index = cell_overlap.index(max(cell_overlap))
            return adjacent_cells[cell_index]
        return None

    def duplicated_views(self, original_group, duplicating_group):
        original_views = self.window.views_in_group(original_group)
        original_buffers = {v.buffer_id() for v in original_views}
        potential_dupe_views = self.window.views_in_group(duplicating_group)
        dupe_views = []
        for view_to_remove in potential_dupe_views:
            if view_to_remove.buffer_id() in original_buffers:
                dupe_views.append(view_to_remove)
        return dupe_views

    @classmethod
    def tabless_views(cls, window, duplicating_group):
        potential_dupe_views = window.views_in_group(duplicating_group)
        dupe_views = []
        for view_to_remove in potential_dupe_views:
            # print('tabless_views file_name', view_to_remove.file_name(), 'size', view_to_remove.size(), 'name', view_to_remove.name(), 'is_dirty', view_to_remove.is_dirty())
            if cls.is_tabless( view_to_remove ):
                dupe_views.append(view_to_remove)
        return dupe_views

    @staticmethod
    def is_tabless(view):
        return view.size() < 1 and view.name() == '' and view.file_name() is None

    def travel_to_pane(self, direction, create_new_if_necessary=False):
        adjacent_cell = self.adjacent_cell(direction)
        if adjacent_cell:
            cells = self.get_cells()
            new_group_index = cells.index(adjacent_cell)
            self.window.focus_group(new_group_index)
        elif create_new_if_necessary:
            self.create_pane(direction, True)

    def carry_file_to_pane(self, direction, create_new_if_necessary=False):
        view = self.window.active_view()
        if view == None:
            # If we're in an empty group, there's no active view
            return

        window = self.window
        self.travel_to_pane(direction, create_new_if_necessary)

        active_group = window.active_group()
        views_in_group = window.views_in_group(active_group)
        window.set_view_index(view, active_group, len(views_in_group))
        sublime.set_timeout(lambda: window.focus_view(view))

    def clone_file_to_pane(self, direction, create_new_if_necessary=False):
        window = self.window
        view = window.active_view()
        if view == None:
            # If we're in an empty group, there's no active view
            return
        group, original_index = window.get_view_index(view)
        window.run_command('clone_file')

        # If we move the cloned file's tab to the left of the original's,
        # then when we remove it from the group, focus will fall to the
        # original view.
        new_view = window.active_view()
        window.set_view_index(new_view, group, original_index)

        # Fix the new view's selection and viewport
        new_sel = new_view.sel()
        new_sel.clear()
        for s in view.sel():
            new_sel.add(s)
        sublime.set_timeout(lambda : new_view.set_viewport_position(view.viewport_position(), False), 0)

        self.carry_file_to_pane(direction, create_new_if_necessary)

    def reorder_panes(self, leave_files_at_position = True):
        _, _, cells = self.layout()
        current_cell = cells[self.window.active_group()]
        old_index = self.window.active_group()
        on_done = partial(self._on_reorder_done, old_index, leave_files_at_position)
        view = self.window.show_input_panel('enter new index', str(old_index+1), on_done, None, None)
        view.sel().clear()
        view.sel().add(sublime.Region(0, view.size()))

    def _on_reorder_done(self, old_index, leave_files_at_position, text):
        try:
            new_index = int(text) - 1
        except ValueError:
            return

        rows, cols, cells = self.layout()

        if new_index < 0 or new_index >= len(cells):
            return

        cells[old_index], cells[new_index] = cells[new_index], cells[old_index]

        if leave_files_at_position:
            old_files = self.window.views_in_group(old_index)
            new_files = self.window.views_in_group(new_index)
            for position, v in enumerate(old_files):
                self.window.set_view_index(v, new_index, position)
            for position, v in enumerate(new_files):
                self.window.set_view_index(v, old_index, position)

        layout = {'cols': cols, 'rows': rows, 'cells': cells}
        fixed_set_layout(self.window, layout)

    def resize_panes(self, orientation, mode):
        rows, cols, cells = self.layout()

        if orientation == 'cols':
            data = cols
            min1 = YMIN
            max1 = YMAX
            min2 = XMIN
            max2 = XMAX

        elif orientation == 'rows':
            data = rows
            min1 = XMIN
            max1 = XMAX
            min2 = YMIN
            max2 = YMAX

        relevant_indx = set()

        if mode == 'BEFORE':
            current_cell = cells[self.window.active_group()]
            relevant_indx.update(set([current_cell[min2]]))

        elif mode == 'AFTER':
            current_cell = cells[self.window.active_group()]
            relevant_indx.update(set([current_cell[max2]]))

        elif mode == 'NEAREST':
            current_cell = cells[self.window.active_group()]
            relevant_indx.update(set([current_cell[min2], current_cell[max2]]))

        elif mode == 'RELEVANT':
            current_cell = cells[self.window.active_group()]
            min_val1 = current_cell[min1]
            max_val1 = current_cell[max1]
            for c in cells:
                min_val2 = c[min1]
                max_val2 = c[max1]
                if min_val1 >= max_val2 or min_val2 >= max_val1:
                    continue
                relevant_indx.update(set([c[min2], c[max2]]))

        elif mode == 'ALL':
            relevant_indx.update(set(range(len(data))))

        relevant_indx.difference_update(set([0, len(data)-1])) # dont show the first and last value (it's always 0 and 1)
        relevant_indx = sorted(relevant_indx)

        text = ', '.join([str(data[i]) for i in relevant_indx])
        on_done = partial(self._on_resize_panes, orientation, cells, relevant_indx, data)
        on_update = partial(self._on_resize_panes_update, orientation, cells, relevant_indx, data)
        on_cancle = partial(self._on_resize_panes, orientation, cells, relevant_indx, data, text)
        view = self.window.show_input_panel(orientation, text, on_done, on_update, on_cancle)
        view.sel().clear()
        view.sel().add(sublime.Region(0,view.size()))

    def _on_resize_panes_layout(self, orientation, cells, relevant_indx, orig_data, text):
        window = self.window
        rows, cols, _ = self.layout()

        input_data = [float(x) for x in text.split(',')]
        if any(d > 1.0 for d in input_data):
            return {'cols': cols, 'rows': rows, 'cells': cells}

        cells = copy.deepcopy(cells)
        data = copy.deepcopy(orig_data)
        for i, d in zip(relevant_indx, input_data):
            data[i] = d

        data = list(enumerate(data))
        data = sorted(data, key=lambda x: x[1]) # sort such that you can swap grid lines
        indxes, data = map(list, zip(*data)) # indexes are also sorted

        revelant_cell_entries = []
        if orientation == 'cols':
            revelant_cell_entries = [XMIN,XMAX]
        elif orientation == 'rows':
            revelant_cell_entries = [YMIN,YMAX]

        # change the cell boundaries according to the sorted indexes
        transformations = [(old, new) for new, old in enumerate(indxes) if new != old]
        for i in range(len(cells)):
            for j in revelant_cell_entries:
                for old, new in transformations:
                    if cells[i][j] == old:
                        cells[i][j] = new
                        break

        if orientation == 'cols':
            if len(cols) == len(data):
                cols = data
        elif orientation == 'rows':
            if len(rows) == len(data):
                rows = data

        return {'cols': cols, 'rows': rows, 'cells': cells}

    def _on_resize_panes_update(self, orientation, cells, relevant_indx, orig_data, text):
        layout = self._on_resize_panes_layout(orientation, cells, relevant_indx, orig_data, text)
        fixed_set_layout_no_focus_change(self.window, layout)

    def _on_resize_panes(self, orientation, cells, relevant_indx, orig_data, text):
        layout = self._on_resize_panes_layout(orientation, cells, relevant_indx, orig_data, text)
        fixed_set_layout(self.window, layout)

    def zoom_pane(self, fraction, skip_saving):
        window = self.window
        active_group = window.active_group()

        settings = window.settings()
        origami_fraction = settings.get( 'origami_fraction' )
        original_panes_layout = settings.get( 'original_panes_layout' )

        if not skip_saving and ( origami_fraction or original_panes_layout ):
            print('Origami Error: Trying to zoom a zoomed pane!')
            unmaximize_pane( window )
            return

        if fraction is None:
            fraction = .8

        fraction = min(1, max(0, fraction))
        rows,cols,cells = self.layout()

        current_cell = cells[active_group]
        current_col = current_cell[0]
        num_cols = len(cols)-1

        if not skip_saving:
            settings.set( 'original_panes_layout', window.layout() )

        #TODO:  the sizes of the unzoomed panes are calculated incorrectly if the
        #       unzoomed panes have a split that overlaps the zoomed pane.
        current_col_width = 1 if num_cols==1 else fraction
        other_col_width = 0 if num_cols==1 else (1-current_col_width)/(num_cols-1)

        cols = [0.0]
        for i in range(0,num_cols):
            cols.append(cols[i] + (current_col_width if i == current_col else other_col_width))

        current_row = current_cell[1]
        num_rows = len(rows)-1

        current_row_height = 1 if num_rows==1 else fraction
        other_row_height = 0 if num_rows==1 else (1-current_row_height)/(num_rows-1)
        rows = [0.0]
        for i in range(0,num_rows):
            rows.append(rows[i] + (current_row_height if i == current_row else other_row_height))

        layout = {'cols': cols, 'rows': rows, 'cells': cells}
        fixed_set_layout(window, layout)

        settings.set( 'origami_fraction', fraction )
        settings.set( 'max_pane_maximized', None )
        settings.set( 'maximized_pane_group', window.active_group() )

    def unzoom_pane(self):
        window = self.window
        active_group = window.active_group()

        layout = self.settings().get('original_panes_layout')
        remember_panes_layout = self.settings().get('remember_panes_layout')

        window.settings().set( 'origami_fraction', None )
        window.settings().set( 'original_panes_layout', None )
        window.settings().set( 'max_pane_maximized', False )

        if not ( remember_panes_layout and layout ):
            rows,cols,cells = self.layout()
            current_cell = cells[active_group]

            num_cols = len(cols)-1
            col_width = 1.0/num_cols

            cols = [0.0]
            for i in range(0,num_cols):
                cols.append(cols[i] + col_width)

            num_rows = len(rows)-1
            row_height = 1.0/num_rows

            rows = [0.0]
            for i in range(0,num_rows):
                rows.append(rows[i] + row_height)

            layout = {'cols': cols, 'rows': rows, 'cells': cells}

        fixed_set_layout(window, layout)

    def has_zoom(self):
        return is_pane_zoomed( self.window )

    def create_pane(self, direction, give_focus=False):
        has_zoom = self.has_zoom()
        fraction = self.window.settings().get( 'origami_fraction' )

        give_focus = give_focus or has_zoom and not give_focus
        run_unzoomed( self, lambda: self._create_pane( direction, give_focus, has_zoom, fraction ) )

    def _create_pane(self, direction, give_focus, has_zoom, fraction):
        window = self.window
        rows, cols, cells = self.layout()
        active_group = window.active_group()

        old_cell = cells.pop(active_group)
        new_cell = []

        if direction in ('up', 'down'):
            cells = push_down_cells_after(cells, old_cell[YMAX])
            rows.insert(old_cell[YMAX], (rows[old_cell[YMIN]] + rows[old_cell[YMAX]]) / 2)
            new_cell = [old_cell[XMIN], old_cell[YMAX], old_cell[XMAX], old_cell[YMAX]+1]
            old_cell = [old_cell[XMIN], old_cell[YMIN], old_cell[XMAX], old_cell[YMAX]]

        elif direction in ('right', 'left'):
            cells = push_right_cells_after(cells, old_cell[XMAX])
            cols.insert(old_cell[XMAX], (cols[old_cell[XMIN]] + cols[old_cell[XMAX]]) / 2)
            new_cell = [old_cell[XMAX], old_cell[YMIN], old_cell[XMAX]+1, old_cell[YMAX]]
            old_cell = [old_cell[XMIN], old_cell[YMIN], old_cell[XMAX], old_cell[YMAX]]

        if new_cell:
            if direction in ('left', 'up'):
                focused_cell = new_cell
                unfocused_cell = old_cell
            else:
                focused_cell = old_cell
                unfocused_cell = new_cell
            cells.insert(active_group, focused_cell)
            cells.append(unfocused_cell)
            layout = {'cols': cols, 'rows': rows, 'cells': cells}
            fixed_set_layout(window, layout)

            if give_focus:
                self.travel_to_pane(direction)

        if has_zoom and not self.settings().get('unzoom_after_creating_pane', False):
            maximize_pane( window, fraction )

    def _destroy_current_pane(self, has_zoom, fraction):
        #Out of the four adjacent panes, one was split to create this pane.
        #Find out which one, move to it, then destroy this pane.
        cells = self.get_cells()

        current = cells[self.window.active_group()]
        choices = {}
        choices['up'] = self.adjacent_cell('up')
        choices['right'] = self.adjacent_cell('right')
        choices['down'] = self.adjacent_cell('down')
        choices['left'] = self.adjacent_cell('left')

        target_dir = None
        for dir,c in choices.items():
            if not c:
                continue
            if dir in ['up', 'down']:
                if c[XMIN] == current[XMIN] and c[XMAX] == current[XMAX]:
                    target_dir = dir
            elif dir in ['left', 'right']:
                if c[YMIN] == current[YMIN] and c[YMAX] == current[YMAX]:
                    target_dir = dir
        if target_dir:
            self.travel_to_pane(target_dir)
            self._destroy_pane( opposite_direction( target_dir ), has_zoom, fraction )

    def destroy_pane(self, direction):
        has_zoom = self.has_zoom()
        fraction = self.window.settings().get( 'origami_fraction' )
        run_unzoomed( self, lambda: self._destroy_pane( direction, has_zoom, fraction ) )

    def _destroy_pane(self, direction, has_zoom, fraction):
        if direction == 'self':
            self._destroy_current_pane( has_zoom, fraction )
            return

        window = self.window
        rows, cols, cells = self.layout()
        active_group = window.active_group()

        cell_to_remove = None
        current_cell = cells[active_group]

        adjacent_cells = cells_adjacent_to_cell_in_direction(cells, current_cell, direction)
        if len(adjacent_cells) == 1:
            cell_to_remove = adjacent_cells[0]

        if cell_to_remove:
            active_view = window.active_view()
            group_to_remove = cells.index(cell_to_remove)
            # dupe_views = self.duplicated_views(active_group, group_to_remove)
            dupe_views = self.tabless_views(window, group_to_remove)

            # print('destroy_pane dupe_views', dupe_views)
            for view_to_remove in dupe_views:
                window.focus_view(view_to_remove)
                window.run_command('close')

            if active_view:
                window.focus_view(active_view)

            cells.remove(cell_to_remove)
            if direction == 'up':
                rows.pop(cell_to_remove[YMAX])
                adjacent_cells = cells_adjacent_to_cell_in_direction(cells, cell_to_remove, 'down')
                for cell in adjacent_cells:
                    cells[cells.index(cell)][YMIN] = cell_to_remove[YMIN]
                cells = pull_up_cells_after(cells, cell_to_remove[YMAX])
            elif direction == 'right':
                cols.pop(cell_to_remove[XMIN])
                adjacent_cells = cells_adjacent_to_cell_in_direction(cells, cell_to_remove, 'left')
                for cell in adjacent_cells:
                    cells[cells.index(cell)][XMAX] = cell_to_remove[XMAX]
                cells = pull_left_cells_after(cells, cell_to_remove[XMIN])
            elif direction == 'down':
                rows.pop(cell_to_remove[YMIN])
                adjacent_cells = cells_adjacent_to_cell_in_direction(cells, cell_to_remove, 'up')
                for cell in adjacent_cells:
                    cells[cells.index(cell)][YMAX] = cell_to_remove[YMAX]
                cells = pull_up_cells_after(cells, cell_to_remove[YMIN])
            elif direction == 'left':
                cols.pop(cell_to_remove[XMAX])
                adjacent_cells = cells_adjacent_to_cell_in_direction(cells, cell_to_remove, 'right')
                for cell in adjacent_cells:
                    cells[cells.index(cell)][XMIN] = cell_to_remove[XMIN]
                cells = pull_left_cells_after(cells, cell_to_remove[XMAX])

            layout = {'cols': cols, 'rows': rows, 'cells': cells}
            fixed_set_layout(window, layout)

        if has_zoom and not self.settings().get('unzoom_after_closing_pane', False):
            maximize_pane( window, fraction )

    def pull_file_from_pane(self, direction):
        adjacent_cell = self.adjacent_cell(direction)

        if adjacent_cell:
            cells = self.get_cells()
            group_index = cells.index(adjacent_cell)

            view = self.window.active_view_in_group(group_index)

            if view:
                active_group_index = self.window.active_group()
                views_in_group = self.window.views_in_group(active_group_index)
                self.window.set_view_index(view, active_group_index, len(views_in_group))


class TravelToPaneCommand(PaneCommand):
    def run(self, direction, create_new_if_necessary=None):
        if create_new_if_necessary is None:
            create_new_if_necessary = self.settings().get('create_new_pane_if_necessary')
        self.travel_to_pane(direction, create_new_if_necessary)


class CarryFileToPaneCommand(PaneCommand):
    def run(self, direction, create_new_if_necessary=None):
        if create_new_if_necessary is None:
            create_new_if_necessary = self.settings().get('create_new_pane_if_necessary')
        self.carry_file_to_pane(direction, create_new_if_necessary)


class CloneFileToPaneCommand(PaneCommand):
    def run(self, direction, create_new_if_necessary=None):
        if create_new_if_necessary is None:
            create_new_if_necessary = self.settings().get('create_new_pane_if_necessary')
        self.clone_file_to_pane(direction, create_new_if_necessary)


class CreatePaneWithFileCommand(PaneCommand):
    def run(self, direction):
        self.create_pane(direction)
        self.carry_file_to_pane(direction)


class CreatePaneWithClonedFileCommand(PaneCommand):
    def run(self, direction):
        self.create_pane(direction)
        self.clone_file_to_pane(direction)


class PullFileFromPaneCommand(PaneCommand):
    def run(self, direction):
        self.pull_file_from_pane(direction)


class ZoomPaneCommand(PaneCommand):
    def run(self, fraction=None, skip_saving=False):
        self.zoom_pane(fraction, skip_saving)


class UnzoomPaneCommand(PaneCommand):
    def run(self):
        self.unzoom_pane()


class ToggleZoomPaneCommand(sublime_plugin.WindowCommand):
    def run(self, fraction=None):
        window = self.window
        settings = window.settings()
        max_pane_maximized = settings.get( 'max_pane_maximized' )
        origami_fraction = settings.get( 'origami_fraction' )
        original_panes_layout = settings.get( 'original_panes_layout' )

        # print( 'max_pane max_pane_maximized %-5s, origami_fraction: %-5s, original_panes_layout, %-5s' % ( max_pane_maximized, origami_fraction, original_panes_layout is not None ) )
        if is_pane_zoomed( window ):

            if origami_fraction:
                window.run_command( 'unzoom_pane' )

            else:

                if max_pane_maximized:
                    window.run_command( 'zoom_pane', { 'fraction': fraction, 'skip_saving': True } )

                else:
                    print( "Origami Error: Invalid zooming state!" )
                    window.run_command( 'unmaximize_pane' )

        else:
            num_groups = window.num_groups()

            if num_groups > 1:
                window.run_command( 'zoom_pane', { 'fraction': fraction } )

            else:
                print( "Origami Error: Cannot zoom a window only with '%s' panes!" % num_groups )


class CreatePaneCommand(PaneCommand):
    def run(self, direction, give_focus=False):
        self.create_pane(direction, give_focus)


class DestroyPaneCommand(PaneCommand):
    def run(self, direction):
        self.destroy_pane(direction)


class ResizePaneCommand(PaneCommand):
    def run(self, orientation, mode = None):
        if mode == None:
            mode = 'NEAREST'
        self.resize_panes(orientation, mode)


class ReorderPaneCommand(PaneCommand):
    def run(self):
        self.reorder_panes()


class SaveLayoutCommand(PaneCommand):
    """ Save the current layout configuration in a settings file. """

    def __init__(self, window):
        self.window = window
        super(SaveLayoutCommand, self).__init__(window)

    def on_done(self, nickname):
        saved_layouts = self.settings().get('saved_layouts')
        layout_names = [l['nickname'] for l in saved_layouts]
        layout_data = self.layout()

        if nickname in layout_names:
            dialog_str = ("You already have a layout stored as '{0}'.\n\n"
                          "Do you want to continue and overwrite that "
                          "layout?".format(nickname))
            dialog_btn = "Overwrite layout"

            if sublime.ok_cancel_dialog(dialog_str, dialog_btn):
                def get_index(seq, attr, value):
                    return next(i for (i, d) in enumerate(seq) if d[attr] == value)

                layout = saved_layouts[get_index(saved_layouts, 'nickname', nickname)]
                layout['rows'] = layout_data[0]
                layout['cols'] = layout_data[1]
                layout['cells'] = layout_data[2]
            else:
                self.window.run_command('save_layout')
                return
        else:
            layout = {}
            layout['nickname'] = nickname
            layout['rows'] = layout_data[0]
            layout['cols'] = layout_data[1]
            layout['cells'] = layout_data[2]
            saved_layouts.append(layout)

        self.settings().set('saved_layouts', saved_layouts)
        sublime.save_settings('Origami.sublime-settings')

    def run(self):
        self.window.show_input_panel(
            'Window layout nickname:',
            '',
            self.on_done,
            None,
            None
        )


class RestoreLayoutCommand(PaneCommand):
    """ Restore a saved layout from a settings file. """

    def __init__(self, window):
        self.window = window
        super(RestoreLayoutCommand, self).__init__(window)

    def on_done(self, index):
        saved_layouts = self.settings().get('saved_layouts')

        if index != -1:
            selected_layout = saved_layouts[index]
            layout = {}
            layout['cells'] = selected_layout['cells']
            layout['cols'] = selected_layout['cols']
            layout['rows'] = selected_layout['rows']
            fixed_set_layout(self.window, layout)

    def run(self):
        if self.settings().has('saved_layouts'):
            saved_layouts = self.settings().get('saved_layouts')
            layout_names = [l['nickname'] for l in saved_layouts]
            self.window.show_quick_panel(layout_names, self.on_done)


class RemoveLayoutCommand(PaneCommand):
    """ Remove a previously saved layout from your settings file. """

    def __init__(self, window):
        self.window = window
        super(RemoveLayoutCommand, self).__init__(window)

    def on_done(self, index):
        saved_layouts = self.settings().get('saved_layouts')

        if index != -1:
            saved_layouts.pop(index)
            self.settings().set('saved_layouts', saved_layouts)
            sublime.save_settings('Origami.sublime-settings')

    def run(self):
        if self.settings().has('saved_layouts'):
            saved_layouts = self.settings().get('saved_layouts')
            layout_names = [l['nickname'] for l in saved_layouts]
            self.window.show_quick_panel(layout_names, self.on_done)


class NewWindowFromSavedLayoutCommand(PaneCommand):
    """ Brings up a list of saved views and allows the user
    to create a new window using that layout. """

    def __init__(self, window):
        self.window = window
        super(NewWindowFromSavedLayoutCommand, self).__init__(window)

    def on_done(self, index):
        saved_layouts = self.settings().get('saved_layouts')

        if index != -1:
            selected_layout = saved_layouts[index]
            layout = {}
            layout['cells'] = selected_layout['cells']
            layout['cols'] = selected_layout['cols']
            layout['rows'] = selected_layout['rows']

            self.window.run_command('new_window')
            new_window = sublime.active_window()
            fixed_set_layout(new_window, layout)

    def run(self):
        if self.settings().has('saved_layouts'):
            saved_layouts = self.settings().get('saved_layouts')
            layout_names = [l['nickname'] for l in saved_layouts]
            self.window.show_quick_panel(layout_names, self.on_done)


class NewWindowWithCurrentLayoutCommand(PaneCommand):
    """ Opens a new window using the current layout settings. """

    def __init__(self, window):
        self.window = window
        super(NewWindowWithCurrentLayoutCommand, self).__init__(window)

    def run(self):
        layout = self.window.layout()
        self.window.run_command('new_window')
        new_window = sublime.active_window()
        fixed_set_layout(new_window, layout)


class AutoCloseEmptyPanes(sublime_plugin.EventListener, WithSettings):
    def is_tabless_view(self, view):
        """ When you make a new pane, it comes with a tabless view that gets a tab when you type
        into it. You also get a similar view when using the command palette to open a file.
        If we think it's this kind of view, return True."""
        if sublime.version()[0] == '2':
            return False
        else:
            window = view.window() or sublime.active_window()
            if window and window.get_view_index(view)[1] == -1:
                return True
        return False

    def on_close(self, view):
        if sublime.version()[0] == '2':
            self.on_pre_close(view)

    def on_pre_close(self, view):
        # Read from global settings for backward compatibility
        auto_close = view.settings().get('origami_auto_close_empty_panes', False)
        auto_close = self.settings().get('auto_close_empty_panes', auto_close)

        if self.is_tabless_view(view):
            # We don't want to close the pane when closing a transient view
            return

        window = sublime.active_window()
        active_group = window.active_group()

        # We're in pre_close, so use set_timeout to close the group right after this.
        if len(window.views_in_group(active_group)) < 2:

            if auto_close:
                sublime.set_timeout( lambda: window.run_command('destroy_pane', {'direction':'self'}), 100 )


class AutoZoomOnFocus(sublime_plugin.EventListener, WithSettings):
    running = False
    active_group = -1

    def delayed_zoom(self, view, fraction):
        # zoom_pane hangs sublime if you destroy the pane above or to your left.
        # call it in a sublime.set_timeout to fix the issue

        # Sublime Text 2 has issues on startup where views don't have windows yet.
        # If we don't have a window yet, bail.
        if view.window() is None:
            self.running = False
            return

        args = {}
        # Work correctly if someone sets 'origami_auto_zoom_on_focus': true rather
        # than e.g. 'origami_auto_zoom_on_focus': .8.
        if fraction != True:
            args['fraction'] = fraction
        view.window().run_command('zoom_pane', args)
        self.running = False

    def on_activated(self, view):
        if self.running:
            return
        # Read from global settings for backward compatibility
        fraction = view.settings().get('origami_auto_zoom_on_focus', False)
        fraction = self.settings().get('auto_zoom_on_focus', fraction)

        if not fraction:
            return

        if view.settings().get('is_widget'):
            return

        new_active_group = view.window().active_group()
        if new_active_group == self.active_group:
            return

        self.active_group = new_active_group
        self.running = True

        sublime.set_timeout(lambda: self.delayed_zoom(view, fraction), 0)


class OrigamiMoveToGroupCommand(PaneCommand):

    def run(self, group):
        window = self.window

        def move():
            time.sleep(0.1)

            # print('running move')
            window.run_command( 'move_to_group', { 'group': group } )
            threading.Thread(target=focus).start()

        def focus():
            time.sleep(0.2)

            # print('running focus')
            window.run_command( 'focus_group', { 'group': group } )

        threading.Thread(target=move).start()

