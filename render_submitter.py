import hou
import os
import csv
import json
import time
import subprocess
import random
from datetime import datetime, timedelta
from PySide2 import QtWidgets, QtCore, QtGui
class ShotSelectionDialog(QtWidgets.QDialog):
    def __init__(self, csv_path, preselected_shot_names=None, parent=None):
        super(ShotSelectionDialog, self).__init__(parent)
        self.csv_path = csv_path
        self.selected_shot_names = set(preselected_shot_names) if preselected_shot_names else set()
        self.all_shot_names = set()  # Store all shot names for search functionality
        self.original_data = []  # Store original data for filtering
        self.shot_groups = {}  # Store shot groups: {group_name: [shot_names]}
        self.shot_tags = {}  # Store shot tags: {shot_name: [group_names]}
        self.group_colors = {}  # Store colors for each group
        self.group_file = os.path.join(os.path.dirname(csv_path), "shot_groups.json")  # File to store groups
        self.setWindowTitle("Select Shots to Render")
        self.setMinimumSize(1000, 800)  # Increased size to accommodate grouping
        self.init_ui()
        self.load_csv_data()
        # Add these variables to track progress
        self.progress_file_path = None
        self.last_render_mode = None
        self.last_shot_index = 0
        self.last_frame = 0
        self.last_engine = None
        self.load_groups()  # Load existing groups from file
        
    def init_ui(self):
        layout = QtWidgets.QVBoxLayout()
        # -----------------------------
        # Title Label
        # -----------------------------
        title_label = QtWidgets.QLabel("Select Shots from CSV File")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2196F3; padding: 10px;")
        title_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title_label)
        # -----------------------------
        # Group Controls
        # -----------------------------
        group_layout = QtWidgets.QHBoxLayout()
        group_layout.addWidget(QtWidgets.QLabel("Group:"))
        self.group_combo = QtWidgets.QComboBox()
        self.group_combo.setEditable(True)
        self.group_combo.addItem("-- All Shots --")
        self.group_combo.currentTextChanged.connect(self.filter_by_group)
        group_layout.addWidget(self.group_combo)
        self.add_group_button = QtWidgets.QPushButton("Add Group")
        self.add_group_button.clicked.connect(self.add_group)
        group_layout.addWidget(self.add_group_button)
        self.remove_group_button = QtWidgets.QPushButton("Remove Group")
        self.remove_group_button.clicked.connect(self.remove_group)
        group_layout.addWidget(self.remove_group_button)
        self.add_to_group_button = QtWidgets.QPushButton("Add Selected to Group")
        self.add_to_group_button.clicked.connect(self.add_selected_to_group)
        group_layout.addWidget(self.add_to_group_button)
        layout.addLayout(group_layout)
        # -----------------------------
        # Search Box
        # -----------------------------
        search_layout = QtWidgets.QHBoxLayout()
        search_layout.addWidget(QtWidgets.QLabel("Search:"))
        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText("Type to filter shots...")
        self.search_box.textChanged.connect(self.filter_table)
        search_layout.addWidget(self.search_box)
        self.clear_search_button = QtWidgets.QPushButton("Clear")
        self.clear_search_button.clicked.connect(self.clear_search)
        search_layout.addWidget(self.clear_search_button)
        layout.addLayout(search_layout)
        # -----------------------------
        # Selection Info Label
        # -----------------------------
        self.selection_info_label = QtWidgets.QLabel("0 shots selected")
        self.selection_info_label.setStyleSheet("color: gray;")
        layout.addWidget(self.selection_info_label)
        # -----------------------------
        # Table Widget (with Multi-Selection)
        # -----------------------------
        self.table_widget = QtWidgets.QTableWidget()
        self.table_widget.setColumnCount(1)
        self.table_widget.setHorizontalHeaderLabels(["Select"])
        self.table_widget.horizontalHeader().setStretchLastSection(True)
        self.table_widget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table_widget.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table_widget.setSortingEnabled(True)  # Allow sorting by column
        self.table_widget.horizontalHeader().sectionClicked.connect(self.on_header_clicked)
        # Enable multi-row selection with Ctrl/Shift
        self.table_widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        # Install event filter for advanced checkbox handling (Shift+Click, Ctrl+Click)
        self.table_widget.viewport().installEventFilter(self)
        layout.addWidget(self.table_widget)
        # -----------------------------
        # Buttons (Selection + OK/Cancel)
        # -----------------------------
        buttons_layout = QtWidgets.QHBoxLayout()
        self.select_all_button = QtWidgets.QPushButton("Select All")
        self.select_all_button.clicked.connect(self.select_all)
        self.deselect_all_button = QtWidgets.QPushButton("Deselect All")
        self.deselect_all_button.clicked.connect(self.deselect_all)
        self.invert_selection_button = QtWidgets.QPushButton("Invert Selection")
        self.invert_selection_button.clicked.connect(self.invert_selection)
        self.save_button = QtWidgets.QPushButton("Save Selection")
        self.save_button.clicked.connect(self.accept)
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(self.select_all_button)
        buttons_layout.addWidget(self.deselect_all_button)
        buttons_layout.addWidget(self.invert_selection_button)
        buttons_layout.addWidget(self.save_button)
        buttons_layout.addWidget(self.cancel_button)
        layout.addLayout(buttons_layout)
        # -----------------------------
        # Export / Import Buttons
        # -----------------------------
        import_export_layout = QtWidgets.QHBoxLayout()
        self.export_button = QtWidgets.QPushButton("Export Selection")
        self.export_button.clicked.connect(self.export_selection)
        self.import_button = QtWidgets.QPushButton("Import Selection")
        self.import_button.clicked.connect(self.import_selection)
        import_export_layout.addWidget(self.export_button)
        import_export_layout.addWidget(self.import_button)
        layout.addLayout(import_export_layout)
        # -----------------------------
        # Finalize Layout
        # -----------------------------
        self.setLayout(layout)
    def eventFilter(self, obj, event):
        if obj is self.table_widget.viewport() and event.type() == QtCore.QEvent.MouseButtonPress:
            # Get the row that was clicked
            index = self.table_widget.indexAt(event.pos())
            if not index.isValid():
                return super(ShotSelectionDialog, self).eventFilter(obj, event)
            
            row = index.row()
            col = index.column()
            
            # Check if the click was on the checkbox column (column 0)
            if col == 0:
                # Get the checkbox widget
                checkbox = self.table_widget.cellWidget(row, col)
                if checkbox:
                    # Handle different modifier keys
                    if event.modifiers() & QtCore.Qt.ControlModifier:
                        # Toggle the checkbox
                        checkbox.setChecked(not checkbox.isChecked())
                    elif event.modifiers() & QtCore.Qt.ShiftModifier:
                        # Get the current selection
                        selected_rows = set()
                        for r in range(self.table_widget.rowCount()):
                            cb = self.table_widget.cellWidget(r, 0)
                            if cb and cb.isChecked():
                                selected_rows.add(r)
                        
                        if selected_rows:
                            # Find the closest selected row
                            closest_row = min(selected_rows, key=lambda x: abs(x - row))
                            
                            # Determine the range
                            start_row = min(closest_row, row)
                            end_row = max(closest_row, row)
                            
                            # Set all checkboxes in the range to checked
                            for r in range(start_row, end_row + 1):
                                cb = self.table_widget.cellWidget(r, 0)
                                if cb:
                                    cb.setChecked(True)
                        else:
                            # If no rows are selected, just toggle this one
                            checkbox.setChecked(not checkbox.isChecked())
                    else:
                        # Normal click - toggle just this checkbox
                        checkbox.setChecked(not checkbox.isChecked())
                    
                    # Update selection count
                    self.update_selection_count()
                    return True  # Event handled
        
        return super(ShotSelectionDialog, self).eventFilter(obj, event)
        
    def load_groups(self):
        """Load groups from file if it exists"""
        if os.path.exists(self.group_file):
            try:
                with open(self.group_file, 'r') as f:
                    data = json.load(f)
                    self.shot_groups = data.get('groups', {})
                    self.group_colors = {name: QtGui.QColor(*color) for name, color in data.get('colors', {}).items()}
                    
                    # Build shot_tags dictionary
                    self.shot_tags = {}
                    for group_name, shot_names in self.shot_groups.items():
                        for shot_name in shot_names:
                            if shot_name not in self.shot_tags:
                                self.shot_tags[shot_name] = []
                            if group_name not in self.shot_tags[shot_name]:
                                self.shot_tags[shot_name].append(group_name)
                    
                    # Update combo box with loaded groups
                    for group_name in self.shot_groups.keys():
                        if group_name not in [self.group_combo.itemText(i) for i in range(self.group_combo.count())]:
                            self.group_combo.addItem(group_name)
                            
                    # Refresh table to show group colors
                    self.refresh_table_colors()
            except Exception as e:
                print(f"Error loading groups: {str(e)}")
                
    def save_groups(self):
        """Save groups to file"""
        try:
            data = {
                'groups': self.shot_groups,
                'colors': {name: [color.red(), color.green(), color.blue()] for name, color in self.group_colors.items()}
            }
            with open(self.group_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving groups: {str(e)}")
    def load_csv_data(self):
        try:
            with open(self.csv_path, 'r', newline='', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames
                
                if not headers:
                    QtWidgets.QMessageBox.warning(self, "Warning", "CSV file is empty or has no headers.")
                    return
                
                # Set up table with headers
                self.table_widget.setColumnCount(len(headers) + 1)  # +1 for checkbox column
                header_labels = ["Select"] + headers
                self.table_widget.setHorizontalHeaderLabels(header_labels)
                
                # Find shot name column index - handle variations in naming
                self.shot_name_column_idx = None
                for i, header in enumerate(headers):
                    if header.lower() in ["shot names", "shot name", "shot"]:
                        self.shot_name_column_idx = i + 1  # +1 because of checkbox column
                        break
                
                if self.shot_name_column_idx is None:
                    # Default to first data column if shot names column not found
                    self.shot_name_column_idx = 1
                
                # Store original data and populate table
                self.original_data = []
                self.table_widget.setRowCount(0)
                for row_idx, row in enumerate(reader):
                    self.table_widget.insertRow(row_idx)
                    
                    # Store shot name
                    shot_name = row.get(headers[self.shot_name_column_idx-1], "")
                    self.all_shot_names.add(shot_name)
                    
                    # Add checkbox in first column
                    checkbox = QtWidgets.QCheckBox()
                    # Check if this shot was previously selected
                    if shot_name in self.selected_shot_names:
                        checkbox.setChecked(True)
                    self.table_widget.setCellWidget(row_idx, 0, checkbox)
                    
                    # Add data for each column
                    row_data = [shot_name]  # Store shot name for filtering
                    for col_idx, header in enumerate(headers):
                        item = QtWidgets.QTableWidgetItem(row.get(header, ""))
                        self.table_widget.setItem(row_idx, col_idx + 1, item)
                        row_data.append(row.get(header, ""))
                    
                    self.original_data.append(row_data)
                
                # Resize columns to content
                self.table_widget.resizeColumnsToContents()
                
                # Update selection count
                self.update_selection_count()
                
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load CSV data: {str(e)}")
    
    def add_group(self):
        group_name, ok = QtWidgets.QInputDialog.getText(
            self, "Add Group", "Enter group name:"
        )
        if not ok:
            return
        group_name = group_name.strip()
        if not group_name:
            QtWidgets.QMessageBox.warning(self, "Add Group", "Group name cannot be empty.")
            return
        if group_name in self.shot_groups:
            QtWidgets.QMessageBox.warning(self, "Add Group", f"Group '{group_name}' already exists.")
            return
        # Create empty group and a readable random color
        self.shot_groups[group_name] = []
        color = QtGui.QColor(
            random.randint(120, 230),
            random.randint(120, 230),
            random.randint(120, 230)
        )
        self.group_colors[group_name] = color
        # Add to combo if not present, and select it
        if self.group_combo.findText(group_name) < 0:
            self.group_combo.addItem(group_name)
        self.group_combo.setCurrentText(group_name)
        self.save_groups()
        self.refresh_table_colors()
        QtWidgets.QMessageBox.information(self, "Add Group", f"Group '{group_name}' created successfully.")
    
    def remove_group(self):
        current_text = self.group_combo.currentText()
        if current_text == "-- All Shots --":
            QtWidgets.QMessageBox.warning(self, "Remove Group", "Cannot remove the 'All Shots' entry.")
            return
        reply = QtWidgets.QMessageBox.question(
            self, "Remove Group",
            f"Are you sure you want to remove the group '{current_text}'?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        # Remove this group from shot_tags for each shot
        if current_text in self.shot_groups:
            for shot_name in list(self.shot_groups[current_text]):
                if shot_name in self.shot_tags:
                    try:
                        self.shot_tags[shot_name].remove(current_text)
                    except ValueError:
                        pass
                    if not self.shot_tags[shot_name]:
                        del self.shot_tags[shot_name]
        # Remove from group dicts
        if current_text in self.shot_groups:
            del self.shot_groups[current_text]
        if current_text in self.group_colors:
            del self.group_colors[current_text]
        # Remove combo entry
        idx = self.group_combo.findText(current_text)
        if idx >= 0:
            self.group_combo.removeItem(idx)
        # Reset combo to All Shots and refresh visuals
        self.group_combo.setCurrentIndex(0)
        self.save_groups()
        self.refresh_table_colors()
        QtWidgets.QMessageBox.information(self, "Remove Group", f"Group '{current_text}' removed.")
    
    def add_selected_to_group(self):
        current_text = self.group_combo.currentText()
        if current_text == "-- All Shots --":
            QtWidgets.QMessageBox.warning(
                self, "Add to Group", 
                "Please select or create a group first."
            )
            return
        
        # Get selected shots
        selected_shots = []
        for row in range(self.table_widget.rowCount()):
            if not self.table_widget.isRowHidden(row):
                checkbox = self.table_widget.cellWidget(row, 0)
                if checkbox and checkbox.isChecked():
                    item = self.table_widget.item(row, self.shot_name_column_idx)
                    if item:
                        # Get the original shot name (without group tags)
                        shot_name = item.text().split("[")[0].strip()
                        selected_shots.append(shot_name)
        
        if not selected_shots:
            QtWidgets.QMessageBox.warning(
                self, "Add to Group", 
                "No shots selected."
            )
            return
        
        # Add shots to group
        if current_text not in self.shot_groups:
            self.shot_groups[current_text] = []
        
        added_count = 0
        for shot in selected_shots:
            if shot not in self.shot_groups[current_text]:
                self.shot_groups[current_text].append(shot)
                added_count += 1
                
                # Update shot_tags
                if shot not in self.shot_tags:
                    self.shot_tags[shot] = []
                if current_text not in self.shot_tags[shot]:
                    self.shot_tags[shot].append(current_text)
        
        # Refresh table to show group colors
        self.refresh_table_colors()
        
        # Save groups to file
        self.save_groups()
        
        # Auto-select the group in the combo box to show the filtered view
        self.group_combo.setCurrentText(current_text)
        
        QtWidgets.QMessageBox.information(
            self, "Add to Group", 
            f"Added {added_count} shots to group '{current_text}'."
        )
    def load_groups(self):
        """Load groups from file if it exists"""
        if os.path.exists(self.group_file):
            try:
                with open(self.group_file, 'r') as f:
                    data = json.load(f)
                    self.shot_groups = data.get('groups', {})
                    self.group_colors = {name: QtGui.QColor(*color) for name, color in data.get('colors', {}).items()}
                    
                    # Build shot_tags dictionary
                    self.shot_tags = {}
                    for group_name, shot_names in self.shot_groups.items():
                        for shot_name in shot_names:
                            if shot_name not in self.shot_tags:
                                self.shot_tags[shot_name] = []
                            if group_name not in self.shot_tags[shot_name]:
                                self.shot_tags[shot_name].append(group_name)
                    
                    # Update combo box with loaded groups
                    for group_name in self.shot_groups.keys():
                        if group_name not in [self.group_combo.itemText(i) for i in range(self.group_combo.count())]:
                            self.group_combo.addItem(group_name)
                            
                    # Refresh table to show group colors
                    self.refresh_table_colors()
            except Exception as e:
                print(f"Error loading groups: {str(e)}")
    
    def filter_by_group(self, group_name):
        # Reset all row visibility first
        for row in range(self.table_widget.rowCount()):
            self.table_widget.setRowHidden(row, False)
        
        # If not "All Shots", filter by group
        if group_name != "-- All Shots --":
            # Get shots in the selected group
            group_shots = self.shot_groups.get(group_name, set())
            
            # Hide rows not in the group
            for row in range(self.table_widget.rowCount()):
                item = self.table_widget.item(row, self.shot_name_column_idx)
                if item:
                    shot_name = item.text()
                    if shot_name not in group_shots:
                        self.table_widget.setRowHidden(row, True)
        
        # Update selection count for visible rows
        self.update_selection_count()
    
    def refresh_table_colors(self):
        """Refresh table colors with multi-group support"""
        # First, reset all row colors and restore original shot names
        for row in range(self.table_widget.rowCount()):
            # Get the original shot name
            item = self.table_widget.item(row, self.shot_name_column_idx)
            if item:
                shot_name = item.text()
                # Remove any group tags that might have been added
                if "[" in shot_name:
                    original_name = shot_name.split("[")[0].strip()
                    # Restore the original shot name
                    original_item = QtWidgets.QTableWidgetItem(original_name)
                    self.table_widget.setItem(row, self.shot_name_column_idx, original_item)
            
            # Reset all cell backgrounds and tooltips
            for col in range(self.table_widget.columnCount()):
                cell_item = self.table_widget.item(row, col)
                if cell_item:
                    cell_item.setBackground(QtGui.QBrush())
                    cell_item.setToolTip("")
        
        # Apply group colors and tooltips
        for row in range(self.table_widget.rowCount()):
            item = self.table_widget.item(row, self.shot_name_column_idx)
            if item:
                shot_name = item.text()
                if shot_name in self.shot_tags and self.shot_tags[shot_name]:
                    # Get all groups for this shot
                    groups = self.shot_tags[shot_name]
                    
                    # Create tooltip text
                    tooltip = f"Groups: {', '.join(groups)}"
                    
                    # Apply tooltip to all cells in the row
                    for col in range(self.table_widget.columnCount()):
                        cell_item = self.table_widget.item(row, col)
                        if cell_item:
                            cell_item.setToolTip(tooltip)
                    
                    # Apply color to the entire row
                    if groups:
                        # Use the first group's color
                        first_group = groups[0]
                        color = self.group_colors.get(first_group, QtGui.QColor(200, 200, 200))
                        
                        # Apply color to all cells in the row
                        for col in range(self.table_widget.columnCount()):
                            cell_item = self.table_widget.item(row, col)
                            if cell_item:
                                cell_item.setBackground(color)
                        
                        # Add group tags to the shot name
                        tag_text = " ".join([f"[{group}]" for group in groups])
                        tagged_item = QtWidgets.QTableWidgetItem(f"{shot_name} {tag_text}")
                        tagged_item.setBackground(color)
                        tagged_item.setToolTip(tooltip)
                        self.table_widget.setItem(row, self.shot_name_column_idx, tagged_item)
    
    def export_selection(self):
        selected_shot_names = self.get_selected_shot_names()
        if not selected_shot_names:
            QtWidgets.QMessageBox.information(self, "Export Selection", "No shots selected to export.")
            return
            
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Selection", "", "Text Files (*.txt);;CSV Files (*.csv)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', newline='', encoding='utf-8') as f:
                    if file_path.endswith('.csv'):
                        writer = csv.writer(f)
                        writer.writerow(["Shot Name"])
                        for shot_name in selected_shot_names:
                            writer.writerow([shot_name])
                    else:
                        for shot_name in selected_shot_names:
                            f.write(f"{shot_name}\n")
                QtWidgets.QMessageBox.information(self, "Export Selection", f"Exported {len(selected_shot_names)} shots to {file_path}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Export Error", f"Failed to export selection: {str(e)}")
    
    def import_selection(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import Selection", "", "Text Files (*.txt);;CSV Files (*.csv)"
        )
        
        if file_path:
            try:
                imported_shot_names = set()
                with open(file_path, 'r', encoding='utf-8') as f:
                    if file_path.endswith('.csv'):
                        reader = csv.reader(f)
                        next(reader)  # Skip header
                        for row in reader:
                            if row:
                                imported_shot_names.add(row[0].strip())
                    else:
                        for line in f:
                            shot_name = line.strip()
                            if shot_name:
                                imported_shot_names.add(shot_name)
                
                # Update checkboxes for imported shots
                for row in range(self.table_widget.rowCount()):
                    item = self.table_widget.item(row, self.shot_name_column_idx)
                    if item:
                        shot_name = item.text()
                        checkbox = self.table_widget.cellWidget(row, 0)
                        if checkbox:
                            checkbox.setChecked(shot_name in imported_shot_names)
                
                self.update_selection_count()
                matched_count = len(imported_shot_names & self.all_shot_names)
                QtWidgets.QMessageBox.information(self, "Import Selection", 
                                                f"Imported {len(imported_shot_names)} shots. {matched_count} matched existing shots.")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Import Error", f"Failed to import selection: {str(e)}")
    
    def filter_table(self):
        search_text = self.search_box.text().strip().lower()
        
        # If search is empty, show all rows
        if not search_text:
            for row in range(self.table_widget.rowCount()):
                self.table_widget.setRowHidden(row, False)
                # Reset highlighting
                for col in range(1, self.table_widget.columnCount()):
                    item = self.table_widget.item(row, col)
                    if item:
                        item.setBackground(QtGui.QBrush())
            return
        
        # Filter rows based on search text
        for row in range(self.table_widget.rowCount()):
            match_found = False
            for col in range(1, self.table_widget.columnCount()):
                item = self.table_widget.item(row, col)
                if item and search_text in item.text().lower():
                    match_found = True
                    # Highlight matching text
                    self.highlight_text(item, search_text)
                else:
                    # Reset background for non-matching cells
                    if item:
                        item.setBackground(QtGui.QBrush())
            
            # Show/hide row based on match
            self.table_widget.setRowHidden(row, not match_found)
    
    def highlight_text(self, item, search_text):
        """Highlight matching text in a cell"""
        text = item.text()
        if not text:
            return
            
        # Create a formatted string with highlighted text
        formatted_text = text
        lower_text = text.lower()
        start = 0
        while True:
            pos = lower_text.find(search_text, start)
            if pos == -1:
                break
            # We can't directly highlight part of text in QTableWidgetItem,
            # so we'll highlight the entire cell
            item.setBackground(QtGui.QColor(255, 255, 150))  # Light yellow highlight
            start = pos + len(search_text)
    
    def clear_search(self):
        self.search_box.clear()
        self.filter_table()
    
    def update_selection_count(self):
        selected_count = 0
        for row in range(self.table_widget.rowCount()):
            checkbox = self.table_widget.cellWidget(row, 0)
            if checkbox and checkbox.isChecked():
                selected_count += 1
        self.selection_info_label.setText(f"{selected_count} shots selected")
    
    def select_all(self):
        for row in range(self.table_widget.rowCount()):
            if not self.table_widget.isRowHidden(row):  # Only select visible rows
                checkbox = self.table_widget.cellWidget(row, 0)
                if checkbox:
                    checkbox.setChecked(True)
        self.update_selection_count()
    
    def deselect_all(self):
        for row in range(self.table_widget.rowCount()):
            if not self.table_widget.isRowHidden(row):  # Only deselect visible rows
                checkbox = self.table_widget.cellWidget(row, 0)
                if checkbox:
                    checkbox.setChecked(False)
        self.update_selection_count()
    
    def invert_selection(self):
        for row in range(self.table_widget.rowCount()):
            if not self.table_widget.isRowHidden(row):  # Only invert visible rows
                checkbox = self.table_widget.cellWidget(row, 0)
                if checkbox:
                    checkbox.setChecked(not checkbox.isChecked())
        self.update_selection_count()
    
    def get_selected_shot_names(self):
        selected_shot_names = set()
        for row in range(self.table_widget.rowCount()):
            checkbox = self.table_widget.cellWidget(row, 0)
            if checkbox and checkbox.isChecked():
                item = self.table_widget.item(row, self.shot_name_column_idx)
                if item:
                    selected_shot_names.add(item.text())
        return selected_shot_names
    def on_header_clicked(self, column):
        # Handle column sorting
        if column == 0:  # Don't sort by checkbox column
            self.table_widget.horizontalHeader().setSortIndicator(-1, QtCore.Qt.AscendingOrder)
            return
        
        # Update selection count after sorting
        QtCore.QTimer.singleShot(100, self.update_selection_count)
    # Override accept to save groups when dialog is closed
    def accept(self):
        self.save_groups()
        super(ShotSelectionDialog, self).accept()
    # Override reject to save groups when dialog is cancelled
    def reject(self):
        self.save_groups()
        super(ShotSelectionDialog, self).reject()
class UniversalRenderToolUI(QtWidgets.QDialog):
    def __init__(self, parent=None):        
        super(UniversalRenderToolUI, self).__init__(parent)
        self.setWindowTitle("MANTRA & KARMA RENDER SUBMITTER")
        self.setMinimumWidth(900)
        self.setMinimumHeight(650)
        self.resize(1100, 750)
        self.header_color_index = 0
        self.start_time = None
        self.total_shots = 0
        self.processed_shots = 0
        self.is_dry_run = True
        self.shot_times = []
        self.current_shot_params = {}
        self.required_folders = []
        self.fml_completed = False  # Track if FML render has completed
        self.is_auto_run_sequence = False  # Track if we're in auto-run sequence mode
        self.fml_rendered_frames = {}  # Track which frames were rendered in FML pass
        self.selected_shot_names = set()  # Changed from selected_shots_indices
        self.resolution = "4k"  # Global resolution setting (2k or 4k)
        self.init_ui()
    def init_ui(self):
        # Create main layout with splitter
        main_layout = QtWidgets.QVBoxLayout(self)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        main_layout.addWidget(splitter)
        
        # Create top widget for controls
        self.controls_widget = QtWidgets.QWidget()
        self.controls_layout = QtWidgets.QVBoxLayout(self.controls_widget)
        
        # Title
        title_label = QtWidgets.QLabel("MANTRA & KARMA RENDER SUBMITTER")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2196F3; padding: 10px;")
        title_label.setAlignment(QtCore.Qt.AlignCenter)
        self.controls_layout.addWidget(title_label)
        
        # CSV file picker and shot selection - Compact layout
        csv_layout = QtWidgets.QHBoxLayout()
        
        # CSV file selection
        csv_file_layout = QtWidgets.QVBoxLayout()
        csv_file_layout.addWidget(QtWidgets.QLabel("CSV File:"))
        csv_file_row = QtWidgets.QHBoxLayout()
        self.csv_path = QtWidgets.QLineEdit()
        self.csv_path.setPlaceholderText("Select CSV file...")
        csv_button = QtWidgets.QPushButton("Browse")
        csv_button.clicked.connect(self.browse_csv)
        csv_file_row.addWidget(self.csv_path)
        csv_file_row.addWidget(csv_button)
        csv_file_layout.addLayout(csv_file_row)
        csv_layout.addLayout(csv_file_layout, 1)
        
        # Shot selection
        shot_selection_layout = QtWidgets.QVBoxLayout()
        shot_selection_layout.addWidget(QtWidgets.QLabel("Shot Selection:"))
        self.select_shots_button = QtWidgets.QPushButton("Select Shots")
        self.select_shots_button.clicked.connect(self.select_shots)
        self.select_shots_button.setEnabled(False)  # Disabled until CSV is loaded
        shot_selection_layout.addWidget(self.select_shots_button)
        self.selected_shots_label = QtWidgets.QLabel("No shots selected")
        self.selected_shots_label.setStyleSheet("color: gray;")
        shot_selection_layout.addWidget(self.selected_shots_label)
        csv_layout.addLayout(shot_selection_layout, 1)
        
        self.controls_layout.addLayout(csv_layout)
        
        # Folder status label
        self.folder_status_label = QtWidgets.QLabel("")
        self.folder_status_label.setStyleSheet("background-color: #2c2c2c; color: yellow; padding: 5px; border-radius: 3px;")
        self.folder_status_label.setVisible(False)
        self.controls_layout.addWidget(self.folder_status_label)
        
        # Frame and Session selection - Compact
        frame_layout = QtWidgets.QHBoxLayout()
        frame_layout.addWidget(QtWidgets.QLabel("Single Frame:"))
        self.single_frame_spin = QtWidgets.QSpinBox()
        self.single_frame_spin.setMinimum(1)
        self.single_frame_spin.setMaximum(9999)
        self.single_frame_spin.setValue(1)
        frame_layout.addWidget(self.single_frame_spin)
        
        frame_layout.addSpacing(20)
        frame_layout.addWidget(QtWidgets.QLabel("Session Name:"))
        self.session_name_input = QtWidgets.QLineEdit()
        self.session_name_input.setPlaceholderText("default_session")
        frame_layout.addWidget(self.session_name_input)
        
        frame_layout.addStretch()
        self.controls_layout.addLayout(frame_layout)
        
        # Options row with resolution settings - Compact
        options_layout = QtWidgets.QHBoxLayout()
        
        # Left side - Existing options
        left_options = QtWidgets.QHBoxLayout()
        self.dry_run_cb = QtWidgets.QCheckBox("Dry Run")
        self.dry_run_cb.setChecked(True)
        left_options.addWidget(self.dry_run_cb)
        self.show_params_cb = QtWidgets.QCheckBox("Show Parameters")
        self.show_params_cb.setChecked(True)
        left_options.addWidget(self.show_params_cb)
        self.sequence_after_fml_cb = QtWidgets.QCheckBox("Auto-run after FML")
        self.sequence_after_fml_cb.setChecked(True)
        left_options.addWidget(self.sequence_after_fml_cb)
        
        # Add the retry mechanism checkbox
        self.retry_mechanism_cb = QtWidgets.QCheckBox("Enable Retry Mechanism")
        left_options.addWidget(self.retry_mechanism_cb)
        
        # Right side - Resolution settings
        right_options = QtWidgets.QHBoxLayout()
        right_options.addWidget(QtWidgets.QLabel("Resolution:"))
        self.resolution_2k_radio = QtWidgets.QRadioButton("2k")
        self.resolution_4k_radio = QtWidgets.QRadioButton("4k")
        self.resolution_4k_radio.setChecked(True)  # Default to 4k
        # Fixed: Use clicked signal instead of toggled to avoid duplicate logs
        self.resolution_2k_radio.clicked.connect(lambda: self.update_resolution("2k"))
        self.resolution_4k_radio.clicked.connect(lambda: self.update_resolution("4k"))
        right_options.addWidget(self.resolution_2k_radio)
        right_options.addWidget(self.resolution_4k_radio)
        
        options_layout.addLayout(left_options)
        options_layout.addStretch()
        options_layout.addLayout(right_options)
        self.controls_layout.addLayout(options_layout)
        
        # Main buttons row - Compact
        buttons_layout = QtWidgets.QHBoxLayout()
        
        # Render buttons
        self.render_button = QtWidgets.QPushButton("Render All")
        self.render_button.clicked.connect(lambda: self.process_shots(single_frame=None, render_both=True, use_sequence_prefix=False))
        self.render_button.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        buttons_layout.addWidget(self.render_button)
        
        self.single_frame_button = QtWidgets.QPushButton("Single Frame")
        self.single_frame_button.clicked.connect(lambda: self.process_shots(single_frame=self.single_frame_spin.value(), render_both=True, use_sequence_prefix=False))
        self.single_frame_button.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold;")
        buttons_layout.addWidget(self.single_frame_button)
        
        self.fml_button = QtWidgets.QPushButton("FML Render")
        self.fml_button.clicked.connect(self.process_fml_shots)
        self.fml_button.setStyleSheet("background-color: #9C27B0; color: white; font-weight: bold;")
        buttons_layout.addWidget(self.fml_button)
        
        # Utility buttons
        self.open_output_button = QtWidgets.QPushButton("Open Output")
        self.open_output_button.clicked.connect(self.open_output_folder)
        buttons_layout.addWidget(self.open_output_button)
        
        self.clear_log_button = QtWidgets.QPushButton("Clear Log")
        self.clear_log_button.clicked.connect(self.clear_log)
        buttons_layout.addWidget(self.clear_log_button)
        
        # Add the reset progress button
        self.reset_progress_button = QtWidgets.QPushButton("Reset Progress")
        self.reset_progress_button.clicked.connect(self.reset_progress)
        buttons_layout.addWidget(self.reset_progress_button)
        
        self.close_button = QtWidgets.QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        buttons_layout.addWidget(self.close_button)
        
        self.controls_layout.addLayout(buttons_layout)
        
        # Progress bars container
        progress_layout = QtWidgets.QVBoxLayout()
        progress_layout.setContentsMargins(0, 5, 0, 5)
        
        # Shot-level progress bar
        self.shot_progress_label = QtWidgets.QLabel("Shot Progress:")
        self.shot_progress_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        progress_layout.addWidget(self.shot_progress_label)
        
        self.shot_progress_bar = QtWidgets.QProgressBar()
        self.shot_progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #4CAF50;
                border-radius: 3px;
                text-align: center;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
            }
        """)
        self.shot_progress_bar.setVisible(False)
        progress_layout.addWidget(self.shot_progress_bar)
        
        # Frame-level progress bar
        self.frame_progress_label = QtWidgets.QLabel("Frame Progress:")
        self.frame_progress_label.setStyleSheet("color: #2196F3; font-weight: bold;")
        progress_layout.addWidget(self.frame_progress_label)
        
        self.frame_progress_bar = QtWidgets.QProgressBar()
        self.frame_progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #2196F3;
                border-radius: 3px;
                text-align: center;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #2196F3;
            }
        """)
        self.frame_progress_bar.setVisible(False)
        progress_layout.addWidget(self.frame_progress_bar)
        
        self.controls_layout.addLayout(progress_layout)
        
        # Add controls widget to splitter
        splitter.addWidget(self.controls_widget)
        
        # Log area with dark theme
        self.log_area = QtWidgets.QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet("background-color: black; color: white;")
        splitter.addWidget(self.log_area)
        
        # Set splitter sizes - 20% for controls, 80% for log area
        splitter.setSizes([200, 800])
        
    def update_resolution(self, resolution):
        """Update the global resolution setting - Fixed to avoid duplicate logs"""
        # Only log if the radio button is actually checked
        if resolution == "2k" and self.resolution_2k_radio.isChecked():
            self.resolution = "2k"
            self.log_message(f"Resolution set to 2k", "INFO")
        elif resolution == "4k" and self.resolution_4k_radio.isChecked():
            self.resolution = "4k"
            self.log_message(f"Resolution set to 4k", "INFO")
    
    def select_shots(self):
        """Open shot selection dialog"""
        csv_path = self.csv_path.text().strip()
        if not csv_path or not os.path.exists(csv_path):
            self.log_message("Error: Please select a valid CSV file first.", "ERROR")
            return
            
        dialog = ShotSelectionDialog(csv_path, self.selected_shot_names, self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.selected_shot_names = dialog.get_selected_shot_names()
            if self.selected_shot_names:
                self.selected_shots_label.setText(f"{len(self.selected_shot_names)} shots selected")
                self.selected_shots_label.setStyleSheet("color: green;")
                self.log_message(f"Selected {len(self.selected_shot_names)} shots for rendering", "INFO")
            else:
                self.selected_shots_label.setText("No shots selected")
                self.selected_shots_label.setStyleSheet("color: red;")
                self.log_message("No shots selected for rendering", "WARNING")
        else:
            self.log_message("Shot selection cancelled", "INFO")
    
    def browse_csv(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select CSV File", "", "CSV Files (*.csv)"
        )
        if file_path:
            self.csv_path.setText(file_path)
            self.update_button_state()
            self.check_required_folders()
            self.select_shots_button.setEnabled(True)  # Enable shot selection button
            self.selected_shots_indices = []  # Reset selected shots
            self.selected_shots_label.setText("No shots selected")
            self.selected_shots_label.setStyleSheet("color: gray;")
            
    def update_button_state(self):
        csv_path = self.csv_path.text().strip()
        enabled = bool(csv_path and os.path.exists(csv_path))
        self.render_button.setEnabled(enabled)
        self.single_frame_button.setEnabled(enabled)
        self.fml_button.setEnabled(enabled)
        
    def clear_log(self):
        self.log_area.clear()
        
    def open_output_folder(self):
        csv_path = self.csv_path.text().strip()
        if not csv_path or not os.path.exists(csv_path):
            self.log_message("Error: Please select a valid CSV file.", "ERROR")
            return
        input_dir = os.path.dirname(csv_path)
        base_folder = os.path.dirname(input_dir)
        output_dir = os.path.join(base_folder, "Output data")
        if output_dir and os.path.exists(output_dir):
            try:
                subprocess.Popen(f'explorer "{output_dir}"')
            except Exception as e:
                self.log_message(f"Could not open output folder: {str(e)}", "WARNING")
        else:
            self.log_message("Output folder does not exist", "WARNING")
            
    def log_message(self, message, level="INFO"):
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        formatted_message = f"[{ts}] [{level}] {message}"
        self.log_area.append(formatted_message)
        self.log_area.verticalScrollBar().setValue(self.log_area.verticalScrollBar().maximum())
        QtWidgets.QApplication.processEvents()
        
    def get_next_header_color(self):
        colors = [
            "#4A90E2", "#7ED321", "#F5A623", "#D0021B", "#9013FE",
            "#50E3C2", "#F8E71C", "#BD10E0", "#FF6B35", "#1ABC9C"
        ]
        color = colors[self.header_color_index % len(colors)]
        self.header_color_index += 1
        return color
        
    def log_table(self, headers, rows, title=""):
        if title:
            self.log_area.append(f"<h3 style='color: white;'>{title}</h3>")
        header_color = self.get_next_header_color()
        table_html = "<table border='1' cellpadding='5' style='border-collapse: collapse; color: white; background-color: black; margin-bottom: 15px;'>"
        table_html += "<tr>"
        for header in headers:
            table_html += f"<th style='background-color: {header_color}; color: white;'><b>{header}</b></th>"
        table_html += "</tr>"
        for row in rows:
            table_html += "<tr>"
            for cell in row:
                table_html += f"<td style='background-color: black; color: white;'>{cell}</td>"
            table_html += "</tr>"
        table_html += "</table>"
        self.log_area.insertHtml(table_html)
        self.log_area.verticalScrollBar().setValue(self.log_area.verticalScrollBar().maximum())
        QtWidgets.QApplication.processEvents()
        
    def update_eta(self):
        if self.is_dry_run:
            completion = (self.processed_shots / self.total_shots) * 100 if self.total_shots else 0
            self.log_message(f"Progress: {self.processed_shots}/{self.total_shots} ({completion:.1f}%)", "PROGRESS")
            return
        if self.start_time and self.total_shots > 0:
            elapsed_time = time.time() - self.start_time
            completion = (self.processed_shots / self.total_shots) * 100 if self.total_shots else 0
            if self.processed_shots > 0 and self.shot_times:
                avg_time_per_shot = sum(self.shot_times) / len(self.shot_times)
                remaining_shots = max(self.total_shots - self.processed_shots, 0)
                eta_seconds_total = int(avg_time_per_shot * remaining_shots)
                eta_minutes = eta_seconds_total // 60
                eta_seconds = eta_seconds_total % 60
                eta_datetime = datetime.now() + timedelta(seconds=eta_seconds_total)
                self.log_message(
                    f"Progress: {self.processed_shots}/{self.total_shots} ({completion:.1f}%) | "
                    f"Elapsed: {int(elapsed_time//60)}m {int(elapsed_time%60)}s | "
                    f"ETA: {eta_minutes}m {eta_seconds}s | "
                    f"Est. Completion: {eta_datetime.strftime('%H:%M:%S')}",
                    "PROGRESS"
                )
            else:
                self.log_message(
                    f"Progress: {self.processed_shots}/{self.total_shots} ({completion:.1f}%) | "
                    f"Elapsed: {int(elapsed_time//60)}m {int(elapsed_time%60)}s | "
                    f"Calculating ETA...",
                    "PROGRESS"
                )
                
    def check_required_folders(self):
        csv_path = self.csv_path.text().strip()
        if not csv_path or not os.path.exists(csv_path):
            self.folder_status_label.setVisible(False)
            return
           
        input_dir = os.path.dirname(csv_path)
        base_folder = os.path.dirname(input_dir)
       
        required_folders = [
            os.path.join(base_folder, "Parameters"),
            os.path.join(base_folder, "Output data")
        ]
       
        self.required_folders = required_folders
       
        existing_folders = []
        missing_folders = []
       
        for folder in required_folders:
            if os.path.exists(folder):
                existing_folders.append(folder)
            else:
                missing_folders.append(folder)
       
        if missing_folders:
            missing_list = "<br>".join([f"• {folder}" for folder in missing_folders])
            message = (
                "<span style='color: orange; font-weight: bold;'>CAUTION:</span><br>"
                "The following required folders are missing:<br>"
                f"{missing_list}<br><br>"
                "Would you like to create these folders automatically?"
            )
            self.folder_status_label.setText(message)
            self.folder_status_label.setVisible(True)
           
            if hasattr(self, 'create_folders_button'):
                self.create_folders_button.setParent(None)
            self.create_folders_button = QtWidgets.QPushButton("Create Missing Folders")
            self.create_folders_button.setStyleSheet("background-color: #ff9800; color: white; font-weight: bold; padding: 3px;")
            self.create_folders_button.clicked.connect(self.create_missing_folders)
           
            # Fixed: Use the controls_layout directly
            index = self.controls_layout.indexOf(self.folder_status_label)
            self.controls_layout.insertWidget(index + 1, self.create_folders_button)
           
        elif existing_folders:
            existing_list = "<br>".join([f"• {folder}" for folder in existing_folders])
            message = (
                "<span style='color: lightgreen; font-weight: bold;'>CONFIRMATION:</span><br>"
                "Required folders already exist:<br>"
                f"{existing_list}"
            )
            self.folder_status_label.setText(message)
            self.folder_status_label.setVisible(True)
           
            if hasattr(self, 'create_folders_button') and self.create_folders_button:
                self.create_folders_button.setParent(None)
        else:
            self.folder_status_label.setVisible(False)
            
    def create_missing_folders(self):
        for folder in self.required_folders:
            try:
                os.makedirs(folder, exist_ok=True)
                self.log_message(f"Created folder: {folder}", "INFO")
            except Exception as e:
                self.log_message(f"Error creating folder {folder}: {str(e)}", "ERROR")
       
        self.check_required_folders()
        self.log_message("All missing folders have been created successfully!", "INFO")
    def get_progress_file_path(self):
        """Get the path to the progress file with session name"""
        csv_path = self.csv_path.text().strip()
        if not csv_path:
            return None
        input_dir = os.path.dirname(csv_path)
        base_folder = os.path.dirname(input_dir)
        output_dir = os.path.join(base_folder, "Output data")
        os.makedirs(output_dir, exist_ok=True)
        
        # Get session name or use default
        session_name = "default_session"
        if hasattr(self, 'session_name_input') and self.session_name_input:
            text = self.session_name_input.text().strip()
            if text:
                session_name = text
        
        return os.path.join(output_dir, f"render_progress_{session_name}.json")
    def initialize_progress_data(self, mode, shots):
        """Initialize the progress data structure with detailed information"""
        session_name = "default_session"
        if hasattr(self, 'session_name_input') and self.session_name_input:
            text = self.session_name_input.text().strip()
            if text:
                session_name = text
        
        progress_data = {
            "session_name": session_name,
            "mode": mode,
            "resolution": self.resolution,
            "csv_path": self.csv_path.text().strip(),
            "timestamp": datetime.now().isoformat(),
            "shots": []
        }
        
        for shot in shots:
            shot_name = shot["Shot names"]
            frame_range = shot["frame range"]
            
            shot_data = {
                "shot_name": shot_name,
                "status": "pending",  # pending, in_progress, completed, failed
                "engines": {
                    "Karma": {
                        "status": "pending",
                        "frames": {},
                        "failed_frames": {}
                    },
                    "Mantra": {
                        "status": "pending",
                        "frames": {},
                        "failed_frames": {}
                    }
                }
            }
            
            # Initialize frames based on mode
            if mode == "fml":
                # For FML, we only track first, middle, last frames
                fml_frames = [1, (frame_range + 1) // 2, frame_range]
                for frame in fml_frames:
                    shot_data["engines"]["Karma"]["frames"][str(frame)] = {"status": "pending"}
                    shot_data["engines"]["Mantra"]["frames"][str(frame)] = {"status": "pending"}
            else:
                # For full or single frame, track all frames or just the single frame
                if mode in ["full", "auto-run-sequence"]:
                    for frame in range(1, frame_range + 1):
                        shot_data["engines"]["Karma"]["frames"][str(frame)] = {"status": "pending"}
                        shot_data["engines"]["Mantra"]["frames"][str(frame)] = {"status": "pending"}
                elif mode == "single":
                    frame = self.single_frame_spin.value()
                    shot_data["engines"]["Karma"]["frames"][str(frame)] = {"status": "pending"}
                    shot_data["engines"]["Mantra"]["frames"][str(frame)] = {"status": "pending"}
            
            progress_data["shots"].append(shot_data)
        
        return progress_data
    def save_progress(self, shot_name, engine, frame, node_name, status, error=None):
        """Save detailed progress for a specific shot, engine, and frame"""
        if not self.retry_mechanism_cb.isChecked():
            return
            
        progress_file = self.get_progress_file_path()
        if not progress_file:
            return
        
        # Load existing progress data or initialize if it doesn't exist
        try:
            if os.path.exists(progress_file):
                with open(progress_file, 'r') as f:
                    progress_data = json.load(f)
            else:
                # Initialize progress data if file doesn't exist
                return
        except Exception as e:
            self.log_message(f"Error loading progress data: {str(e)}", "ERROR")
            return
        
        # Find the shot in the progress data
        for shot_data in progress_data["shots"]:
            if shot_data["shot_name"] == shot_name:
                # Update the shot status
                if status == "completed":
                    shot_data["status"] = "completed"
                elif status == "failed":
                    shot_data["status"] = "failed"
                else:
                    shot_data["status"] = "in_progress"
                
                # Update the engine status
                engine_data = shot_data["engines"].get(engine)
                if engine_data:
                    if status == "completed":
                        engine_data["status"] = "completed"
                    elif status == "failed":
                        engine_data["status"] = "failed"
                    else:
                        engine_data["status"] = "in_progress"
                    
                    # Update the frame status
                    frame_str = str(frame)
                    if frame_str in engine_data["frames"]:
                        engine_data["frames"][frame_str] = {
                            "status": status,
                            "node": node_name,
                            "timestamp": datetime.now().isoformat()
                        }
                    
                    # If failed, add to failed_frames with error details
                    if status == "failed" and error:
                        engine_data["failed_frames"][frame_str] = {
                            "error": str(error),
                            "node": node_name,
                            "timestamp": datetime.now().isoformat()
                        }
                break
        
        # Save the updated progress data
        try:
            with open(progress_file, 'w') as f:
                json.dump(progress_data, f, indent=2)
        except Exception as e:
            self.log_message(f"Error saving progress: {str(e)}", "ERROR")
    def load_progress(self):
        """Load detailed progress data from file"""
        if not self.retry_mechanism_cb.isChecked():
            return None
            
        progress_file = self.get_progress_file_path()
        if not progress_file or not os.path.exists(progress_file):
            return None
            
        try:
            with open(progress_file, 'r') as f:
                progress_data = json.load(f)
                
            # Verify the CSV file matches
            if progress_data.get("csv_path") != self.csv_path.text().strip():
                self.log_message("Progress file is from a different CSV, ignoring", "WARNING")
                return None
                
            # Verify resolution matches
            if progress_data.get("resolution") != self.resolution:
                self.log_message("Progress file is from a different resolution, ignoring", "WARNING")
                return None
                
            return progress_data
        except Exception as e:
            self.log_message(f"Error loading progress: {str(e)}", "ERROR")
            return None
    def display_progress_summary(self, progress_data):
        """Display a summary of the progress data"""
        if not progress_data:
            return
            
        self.log_message("Progress Summary:", "INFO")
        self.log_message(f"Session: {progress_data.get('session_name', 'Unknown')}", "INFO")
        self.log_message(f"Mode: {progress_data.get('mode', 'Unknown')}", "INFO")
        self.log_message(f"Resolution: {progress_data.get('resolution', 'Unknown')}", "INFO")
        self.log_message(f"Last Updated: {progress_data.get('timestamp', 'Unknown')}", "INFO")
        
        total_shots = len(progress_data.get("shots", []))
        completed_shots = sum(1 for shot in progress_data.get("shots", []) if shot.get("status") == "completed")
        failed_shots = sum(1 for shot in progress_data.get("shots", []) if shot.get("status") == "failed")
        
        self.log_message(f"Shots: {completed_shots} completed, {failed_shots} failed, {total_shots - completed_shots - failed_shots} pending", "INFO")
        
        # Show failed frames details
        for shot in progress_data.get("shots", []):
            for engine_name, engine_data in shot.get("engines", {}).items():
                failed_frames = engine_data.get("failed_frames", {})
                if failed_frames:
                    self.log_message(f"Failed frames in {shot['shot_name']} ({engine_name}):", "WARNING")
                    for frame, frame_data in failed_frames.items():
                        self.log_message(f"  Frame {frame}: {frame_data.get('error', 'Unknown error')} on node {frame_data.get('node', 'Unknown node')}", "WARNING")
    def reset_progress(self):
        """Reset the progress file and progress bars"""
        progress_file = self.get_progress_file_path()
        if progress_file and os.path.exists(progress_file):
            try:
                os.remove(progress_file)
                self.log_message("Progress file reset", "INFO")
            except Exception as e:
                self.log_message(f"Error resetting progress: {str(e)}", "ERROR")
        
        # Reset progress bars
        self.shot_progress_bar.setValue(0)
        self.frame_progress_bar.setValue(0)
    # --------------- Mantra Functions --------------- #
    def get_connected_nodes(self, merge_node, node_type="ifd"):
        nodes = []
        visited_nodes = set()
        def traverse_inputs(node):
            if node.path() in visited_nodes:
                return
            visited_nodes.add(node.path())
            if node.type().name() == node_type:
                nodes.append(node)
                return
            if hasattr(node, 'inputs'):
                for input_node in node.inputs():
                    if input_node:
                        traverse_inputs(input_node)
            elif hasattr(node, 'input'):
                for i in range(10):
                    try:
                        input_node = node.input(i)
                        if input_node:
                            traverse_inputs(input_node)
                        else:
                            break
                    except:
                        break
        try:
            for i in range(10):
                input_node = merge_node.input(i)
                if input_node:
                    traverse_inputs(input_node)
                else:
                    break
        except:
            pass
        return nodes
        
    def node_to_dict(self, node):
        """
        Convert a Houdini node to a dictionary of its parameters, handling complex types.
        """
        node_data = {
            "node_name": node.name(),
            "node_path": node.path(),
            "node_type": node.type().name(),
            "parameters": {}
        }
        for parm in node.parms():
            try:
                # Skip folder-type parameters
                if parm.parmTemplate().type() in [hou.parmTemplateType.Folder, hou.parmTemplateType.FolderSet]:
                    continue
                parm_name = parm.name()
                # Use the safe evaluation function
                parm_value = self.safe_eval(parm)
                node_data["parameters"][parm_name] = parm_value
            except Exception as e:
                # Log the error for debugging, but don't crash
                self.log_message(f"Error evaluating parameter {parm_name} on node {node.path()}: {str(e)}", "WARNING")
                node_data["parameters"][parm_name] = f"ERROR: {str(e)}"
        # Add standard Houdini variables
        node_data["$OS"] = node.name()
        node_data["$HIPNAME"] = hou.hipFile.basename().rsplit('.', 1)[0]
        node_data["$F4"] = "{:04d}".format(int(hou.frame()))
        return node_data
        
    def safe_eval(self, parm):
        """Safely evaluate a Houdini parameter to a JSON-friendly type."""
        try:
            val = parm.eval()
            # Handle tuples (ParmTuple, Vectors, etc.)
            if isinstance(val, (tuple, list)):
                return [self.safe_cast(v) for v in val]
            return self.safe_cast(val)
        except Exception:
            return None  # or return a default value like "" or 0
            
    def safe_cast(self, val):
        """Convert Houdini objects to JSON-friendly types."""
        import hou
        if isinstance(val, hou.Ramp):
            # Convert ramp to dict (positions, values, basis)
            return {
                "type": "ramp",
                "basis": [b.name() for b in val.basis()],
                "keys": [{"pos": k[0], "val": k[1]} for k in val.keys()]
            }
        elif isinstance(val, (hou.Vector2, hou.Vector3, hou.Vector4)):
            return list(val)
        elif isinstance(val, hou.Matrix4):
            return [list(row) for row in val.asTuple()]
        elif isinstance(val, hou.Color):
            return list(val.rgb())
        elif isinstance(val, (str, int, float, bool)):
            return val
        else:
            return str(val)  # fallback: stringify any unknown object
            
    def generate_json_parameters(self, json_dir):
        if not os.path.exists(json_dir):
            os.makedirs(json_dir)
        out_context = hou.node("/out")
        if not out_context:
            self.log_message("Error: /out context not found.", "ERROR")
            return False
        merge_nodes = [node for node in out_context.allSubChildren() if node.type().name() == "merge"]
        if not merge_nodes:
            self.log_message("Error: No merge nodes found in /out.", "ERROR")
            return False
        processed_nodes = set()
        for merge_node in merge_nodes:
            self.log_message(f"Processing merge node: {merge_node.path()}", "INFO")
           
            # Process Mantra nodes
            mantra_nodes = self.get_connected_nodes(merge_node, node_type="ifd")
            self.log_message(f"Found {len(mantra_nodes)} Mantra nodes connected to {merge_node.path()}", "INFO")
            for node in mantra_nodes:
                if node.path() in processed_nodes:
                    continue
                processed_nodes.add(node.path())
                node_name = node.name()
                sanitized_name = "".join(c for c in node_name if c.isalnum() or c in (' ', '-', '_')).rstrip().replace(' ', '_')
                filename = f"{sanitized_name}.json"
                filepath = os.path.join(json_dir, filename)
               
                if os.path.exists(filepath):
                    self.log_message(f"JSON file already exists for {node.path()}: {filename}", "INFO")
                    try:
                        node_data = self.node_to_dict(node)
                        with open(filepath, 'w') as f:
                            json.dump(node_data, f, indent=2)
                        self.log_message(f"Overwritten parameters for {node.path()} to {filepath}", "INFO")
                    except Exception as e:
                        self.log_message(f"Error overwriting {node.path()}: {str(e)}", "ERROR")
                else:
                    try:
                        node_data = self.node_to_dict(node)
                        with open(filepath, 'w') as f:
                            json.dump(node_data, f, indent=2)
                        self.log_message(f"Exported parameters for {node.path()} to {filepath}", "INFO")
                    except Exception as e:
                        self.log_message(f"Error exporting {node.path()}: {str(e)}", "ERROR")
           
            # Process Karma nodes
            karma_nodes = self.get_connected_nodes(merge_node, node_type="karma")
            self.log_message(f"Found {len(karma_nodes)} Karma nodes connected to {merge_node.path()}", "INFO")
            for node in karma_nodes:
                if node.path() in processed_nodes:
                    continue
                processed_nodes.add(node.path())
                node_name = node.name()
                sanitized_name = "".join(c for c in node_name if c.isalnum() or c in (' ', '-', '_')).rstrip().replace(' ', '_')
                filename = f"{sanitized_name}.json"
                filepath = os.path.join(json_dir, filename)
               
                if os.path.exists(filepath):
                    self.log_message(f"JSON file already exists for {node.path()}: {filename}", "INFO")
                    try:
                        node_data = self.node_to_dict(node)
                        with open(filepath, 'w') as f:
                            json.dump(node_data, f, indent=2)
                        self.log_message(f"Overwritten parameters for {node.path()} to {filepath}", "INFO")
                    except Exception as e:
                        self.log_message(f"Error overwriting {node.path()}: {str(e)}", "ERROR")
                else:
                    try:
                        node_data = self.node_to_dict(node)
                        with open(filepath, 'w') as f:
                            json.dump(node_data, f, indent=2)
                        self.log_message(f"Exported parameters for {node.path()} to {filepath}", "INFO")
                    except Exception as e:
                        self.log_message(f"Error exporting {node.path()}: {str(e)}", "ERROR")
        return True
        
    def copy_parameters_from_crowd(self, crowd_node, other_nodes, frame_start, frame_end, resolution_x, resolution_y):
        for node in other_nodes:
            try:
                node.parm("f1").set(frame_start)
                node.parm("f2").set(frame_end)
                node.parm("f3").set(1)
                if self.show_params_cb.isChecked():
                    self.log_message(f"[{node.name()}] Copied frame range: f1={frame_start}, f2={frame_end}, f3=1", "PARAM")
            except Exception as e:
                if self.show_params_cb.isChecked():
                    self.log_message(f"[{node.name()}] Error copying frame range: {str(e)}", "ERROR")
            try:
                # Copy resolution parameters
                if node.parm("override_resolution"):
                    node.parm("override_resolution").set(1)
                if node.parm("res_overridex"):
                    node.parm("res_overridex").set(resolution_x)
                if node.parm("res_overridey"):
                    node.parm("res_overridey").set(resolution_y)
                if self.show_params_cb.isChecked():
                    self.log_message(f"[{node.name()}] Copied resolution: {resolution_x}x{resolution_y}", "PARAM")
            except Exception as e:
                if self.show_params_cb.isChecked():
                    self.log_message(f"[{node.name()}] Error copying resolution: {str(e)}", "ERROR")
                    
    def load_json_parameters(self, json_path):
        try:
            with open(json_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.log_message(f"Error loading JSON {json_path}: {str(e)}", "ERROR")
            return None
            
    def display_shot_parameters(self, shot_name):
        if shot_name not in self.current_shot_params or not self.current_shot_params[shot_name]:
            return
       
        param_headers = ["Node", "Parameter", "Value"]
        param_rows = []
        for node_name, node_data in self.current_shot_params[shot_name].items():
            for param_row in node_data["parameters"]:
                param_rows.append([node_name, param_row[0], param_row[1]])
       
        if param_rows:
            self.log_table(param_headers, param_rows, f"Parameters for Shot: {shot_name}")
       
        config_headers = ["Node", "Config Parameter", "Value"]
        config_rows = []
        for node_name, node_data in self.current_shot_params[shot_name].items():
            for config_row in node_data["config"]:
                config_rows.append([node_name, config_row[0], config_row[1]])
       
        if config_rows:
            self.log_table(config_headers, config_rows, f"Node Configurations for Shot: {shot_name}")
       
        del self.current_shot_params[shot_name]
    # --------------- Karma Functions --------------- #
    def find_lop_networks(self):
        lop_networks = []
        # Search through /obj context
        try:
            obj_context = hou.node("/obj")
            if obj_context:
                for node in obj_context.allNodes():
                    node_type = node.type().name()
                    if node_type in ["lopnet", "lopnet::2.0", "lopnet::1.0"]:
                        lop_networks.append(node)
        except Exception as e:
            self.log_message(f"Error searching LOP networks in /obj: {str(e)}", "ERROR")
        # Search all nodes in the scene
        if not lop_networks:
            try:
                all_nodes = hou.node("/").allNodes()
                for node in all_nodes:
                    node_type = node.type().name()
                    if node_type in ["lopnet", "lopnet::2.0", "lopnet::1.0"]:
                        if node.type().category().name() == "Lop":
                            lop_networks.append(node)
            except Exception as e:
                self.log_message(f"Error searching all nodes for LOP networks: {str(e)}", "ERROR")
        # Try other contexts
        if not lop_networks:
            try:
                contexts_to_check = ["/", "/obj", "/out", "/shop"]
                for context_path in contexts_to_check:
                    context = hou.node(context_path)
                    if context:
                        for node in context.allNodes():
                            node_type = node.type().name()
                            if node_type in ["lopnet", "lopnet::2.0", "lopnet::1.0"]:
                                if node.type().category().name() == "Lop":
                                    lop_networks.append(node)
            except Exception as e:
                self.log_message(f"Error searching alternative contexts: {str(e)}", "ERROR")
        # Remove duplicates
        unique_lop_networks = []
        seen_paths = set()
        for lop_net in lop_networks:
            if lop_net.path() not in seen_paths:
                unique_lop_networks.append(lop_net)
                seen_paths.add(lop_net.path())
        return unique_lop_networks
        
    def get_first_level_children(self, node):
        children = []
        try:
            for child in node.children():
                children.append(child)
        except Exception as e:
            self.log_message(f"Error getting children of {node.path()}: {str(e)}", "ERROR")
        return children
        
    def save_node_parameters_to_json(self, node, json_dir):
        node_name = node.name()
        sanitized_name = "".join(c for c in node_name if c.isalnum() or c in (' ', '-', '_')).rstrip().replace(' ', '_')
        filename = f"{sanitized_name}.json"
        filepath = os.path.join(json_dir, filename)
        if not os.path.exists(filepath):
            node_data = self.node_to_dict(node)
            try:
                os.makedirs(json_dir, exist_ok=True)
                with open(filepath, 'w') as f:
                    json.dump(node_data, f, indent=2)
                self.log_message(f"    Saved parameters to: {filepath}", "INFO")
            except Exception as e:
                self.log_message(f"Error exporting {node.path()}: {str(e)}", "ERROR")
        else:
            self.log_message(f"    JSON file already exists: {filepath}", "INFO")
            
    def analyze_lop_structure(self, json_dir):
        lop_networks = self.find_lop_networks()
        self.log_message("Analyzing LOP networks...", "INFO")
        self.log_message(f"Found {len(lop_networks)} LOP networks:", "INFO")
        for lop_net in lop_networks:
            self.log_message(f"  LOP Network: {lop_net.path()}", "INFO")
            children = self.get_first_level_children(lop_net)
            for child in children:
                self.log_message(f"    Node: {child.name()} | Type: {child.type().name()}", "INFO")
                self.save_node_parameters_to_json(child, json_dir)
                
    def _find_first_node_by_type(self, type_name):
        try:
            for n in hou.node("/").allSubChildren():
                try:
                    if n.type().name() == type_name:
                        return n
                except Exception:
                    continue
        except Exception as e:
            self.log_message(f"Error searching for node type '{type_name}': {str(e)}", "ERROR")
        return None
        
    def get_fml_frames(self, shot):
        """Calculate FML frames for a shot"""
        frame_range = max(int(shot.get("frame range", 1)), 1)
        first_frame = 1
        middle_frame = (frame_range + 1) // 2  # Integer division
        last_frame = frame_range
        return [first_frame, middle_frame, last_frame]
   
    def is_fml_frame(self, frame, shot):
        """Check if a frame is an FML frame for a shot"""
        fml_frames = self.get_fml_frames(shot)
        return frame in fml_frames
   
    def track_fml_render(self, shot_name, frame_num):
        """Track that an FML frame was rendered for a shot"""
        if shot_name not in self.fml_rendered_frames:
            self.fml_rendered_frames[shot_name] = set()
        self.fml_rendered_frames[shot_name].add(frame_num)
   
    def was_fml_rendered(self, shot_name, frame_num):
        """Check if an FML frame was already rendered for a shot"""
        if shot_name not in self.fml_rendered_frames:
            return False
        return frame_num in self.fml_rendered_frames[shot_name]
        
    def apply_mantra_parameters_common(self, node, params, shot_data, dry_run, output_dir=None, use_sequence_prefix=False):
        """Apply common parameters that don't change per frame and return changes"""
        node_name = node.name()
        hip_name = hou.hipFile.basename().rsplit('.', 1)[0]
        shot_name = shot_data.get("Shot names", "unknown_shot")
        
        # In auto-run sequence mode, we don't use sequence prefix
        if use_sequence_prefix and not self.is_auto_run_sequence:
            shot_name = f"Sequence_{shot_name}"
            
        if shot_name not in self.current_shot_params:
            self.current_shot_params[shot_name] = {}
        if node_name not in self.current_shot_params[shot_name]:
            self.current_shot_params[shot_name][node_name] = {"parameters": [], "config": []}
        
        # Track parameter changes for tabular display
        param_changes = []
        
        # Skip frame range parameters
        exclusive_params = ["f1", "f2", "f3"]
        for parm_name, parm_value in params.get("parameters", {}).items():
            if parm_name in exclusive_params:
                continue
            try:
                parm = node.parm(parm_name)
                if parm:
                    if isinstance(parm_value, list):
                        parm.set(tuple(parm_value))
                    else:
                        parm.set(parm_value)
                    if self.show_params_cb.isChecked() and not dry_run:
                        self.current_shot_params[shot_name][node_name]["parameters"].append([parm_name, str(parm_value)])
                    # Add to param_changes for tabular display
                    param_changes.append([parm_name, str(parm_value)])
                elif self.show_params_cb.isChecked():
                    self.current_shot_params[shot_name][node_name]["parameters"].append([parm_name, "NOT FOUND"])
                    param_changes.append([parm_name, "NOT FOUND"])
            except Exception as e:
                if self.show_params_cb.isChecked():
                    self.current_shot_params[shot_name][node_name]["parameters"].append([parm_name, f"ERROR: {str(e)}"])
                    param_changes.append([parm_name, f"ERROR: {str(e)}"])
        
        # Set camera
        camera_path = shot_data.get("camera path")
        if camera_path and node.parm("camera"):
            node.parm("camera").set(camera_path)
            if self.show_params_cb.isChecked():
                self.current_shot_params[shot_name][node_name]["parameters"].append(["camera", camera_path])
            param_changes.append(["camera", camera_path])
        
        # Set output path
        shot_name_output = shot_name  # Use the modified shot name for output path
        render_path = f"{output_dir}/{shot_name_output}/{shot_name_output}.{hip_name}.{node_name}.$F4.exr"
        shot_output_dir = f"{output_dir}/{shot_name_output}"
        if not os.path.exists(shot_output_dir):
            os.makedirs(shot_output_dir)
        
        if node.parm("vm_picture"):
            node.parm("vm_picture").set(render_path)
            if self.show_params_cb.isChecked():
                self.current_shot_params[shot_name][node_name]["parameters"].append(["vm_picture", render_path])
            param_changes.append(["vm_picture", render_path])
        
        # Set resolution based on global setting
        if self.resolution == "2k":
            resolution_x = 2048
            resolution_y = 1432
        else:  # 4k
            resolution_x = 4096
            resolution_y = 2864
            
        # FIXED: Ensure resolution override is enabled and set for all Mantra nodes
        try:
            # Enable resolution override if the parameter exists
            if node.parm("override_resolution"):
                node.parm("override_resolution").set(1)
                if self.show_params_cb.isChecked():
                    self.current_shot_params[shot_name][node_name]["parameters"].append(["override_resolution", "1"])
                param_changes.append(["override_resolution", "1"])
            
            # Set the override resolution parameters
            if node.parm("res_overridex"):
                node.parm("res_overridex").set(resolution_x)
                if self.show_params_cb.isChecked():
                    self.current_shot_params[shot_name][node_name]["parameters"].append(["res_overridex", str(resolution_x)])
                param_changes.append(["res_overridex", str(resolution_x)])
            
            if node.parm("res_overridey"):
                node.parm("res_overridey").set(resolution_y)
                if self.show_params_cb.isChecked():
                    self.current_shot_params[shot_name][node_name]["parameters"].append(["res_overridey", str(resolution_y)])
                param_changes.append(["res_overridey", str(resolution_y)])
            
            # Also set the base resolution as a fallback
            if node.parm("vm_resolutionx"):
                node.parm("vm_resolutionx").set(resolution_x)
                if self.show_params_cb.isChecked():
                    self.current_shot_params[shot_name][node_name]["parameters"].append(["vm_resolutionx", str(resolution_x)])
                param_changes.append(["vm_resolutionx", str(resolution_x)])
            
            if node.parm("vm_resolutiony"):
                node.parm("vm_resolutiony").set(resolution_y)
                if self.show_params_cb.isChecked():
                    self.current_shot_params[shot_name][node_name]["parameters"].append(["vm_resolutiony", str(resolution_y)])
                param_changes.append(["vm_resolutiony", str(resolution_y)])
                
        except Exception as e:
            if self.show_params_cb.isChecked():
                self.current_shot_params[shot_name][node_name]["parameters"].append(["resolution", f"ERROR: {str(e)}"])
                param_changes.append(["resolution", f"ERROR: {str(e)}"])
        
        # Set node-specific configurations
        node_configs = {
            "crowd": {"forceobject": "/obj/RNDR_Crowd_mantra_SH_108"},
            "steps": {"forceobject": "/obj/setps"},
            "shadow_matte": {"forceobject": "/obj/shadow", "phantom_objects": "/obj/RNDR_Crowd_mantra_SH_108"},
            "Flages_matt": {"forceobject": "/obj/poles /obj/red /obj/blue", "matte_objects": "/obj/RNDR_Crowd_mantra_SH_108"}
        }
        
        for config_name, config_params in node_configs.items():
            if config_name.lower() in node_name.lower():
                for parm_name, parm_value in config_params.items():
                    if node.parm(parm_name):
                        node.parm(parm_name).set(parm_value)
                        if self.show_params_cb.isChecked():
                            self.current_shot_params[shot_name][node_name]["config"].append([parm_name, str(parm_value)])
                        param_changes.append([parm_name, str(parm_value)])
                    elif self.show_params_cb.isChecked():
                        self.current_shot_params[shot_name][node_name]["config"].append([parm_name, "NOT FOUND"])
                        param_changes.append([parm_name, "NOT FOUND"])
        
        return param_changes
   
    def apply_mantra_parameters(self, node, params, shot_data, dry_run, single_frame=None, output_dir=None, use_sequence_prefix=False):
        """Apply parameters including frame range and return changes"""
        # Apply common parameters first and get changes
        param_changes = self.apply_mantra_parameters_common(node, params, shot_data, dry_run, output_dir, use_sequence_prefix)
        
        # Set frame range
        if single_frame is not None:
            frame_start = single_frame
            frame_end = single_frame
            self.log_message(f"[{node.name()}] Single frame render mode: frame {single_frame}", "INFO")
        else:
            frame_end = int(shot_data.get("frame range", 1))
            frame_start = 1
        
        node.parm("f1").set(frame_start)
        node.parm("f2").set(frame_end)
        node.parm("f3").set(1)
        
        # Add frame range parameters to changes
        param_changes.append(["f1", str(frame_start)])
        param_changes.append(["f2", str(frame_end)])
        param_changes.append(["f3", "1"])
        
        if self.show_params_cb.isChecked():
            shot_name = shot_data.get("Shot names", "unknown_shot")
            if use_sequence_prefix and not self.is_auto_run_sequence:
                shot_name = f"Sequence_{shot_name}"
            if shot_name not in self.current_shot_params:
                self.current_shot_params[shot_name] = {}
            node_name = node.name()
            if node_name not in self.current_shot_params[shot_name]:
                self.current_shot_params[shot_name][node_name] = {"parameters": [], "config": []}
            self.current_shot_params[shot_name][node_name]["parameters"].append(["f1", str(frame_start)])
            self.current_shot_params[shot_name][node_name]["parameters"].append(["f2", str(frame_end)])
            self.current_shot_params[shot_name][node_name]["parameters"].append(["f3", "1"])
        
        return param_changes
   
    def copy_parameters_from_crowd(self, crowd_node, other_nodes, resolution_x, resolution_y, skip_frame_range=True):
        """Copy parameters from crowd node to other nodes"""
        for node in other_nodes:
            try:
                # Only copy resolution, not frame range
                # FIXED: Ensure resolution override is enabled and set for all copied nodes
                if node.parm("override_resolution"):
                    node.parm("override_resolution").set(1)
                if node.parm("res_overridex"):
                    node.parm("res_overridex").set(resolution_x)
                if node.parm("res_overridey"):
                    node.parm("res_overridey").set(resolution_y)
                # Also set the base resolution as a fallback
                if node.parm("vm_resolutionx"):
                    node.parm("vm_resolutionx").set(resolution_x)
                if node.parm("vm_resolutiony"):
                    node.parm("vm_resolutiony").set(resolution_y)
                if self.show_params_cb.isChecked():
                    self.log_message(f"[{node.name()}] Copied resolution: {resolution_x}x{resolution_y}", "PARAM")
            except Exception as e:
                if self.show_params_cb.isChecked():
                    self.log_message(f"[{node.name()}] Error copying resolution: {str(e)}", "ERROR")
   
    def apply_karma_parameters(self, shot_data, dry_run, single_frame=None, use_sequence_prefix=False, skip_frame_range=False):
        """Apply Karma parameters"""
        shot_name = shot_data.get("Shot names", "unknown_shot")
       
        # In auto-run sequence mode, we don't use sequence prefix
        if use_sequence_prefix and not self.is_auto_run_sequence:
            shot_name = f"Sequence_{shot_name}"
           
        csv_path = self.csv_path.text().strip()
        input_dir = os.path.dirname(csv_path)
        base_folder = os.path.dirname(input_dir)
        output_dir = os.path.join(base_folder, "Output data")
        hip_name = hou.hipFile.basename().rsplit('.', 1)[0]
       
        # Find nodes
        karma_node = self._find_first_node_by_type("karmarenderproperties")
        sceneimport_node = self._find_first_node_by_type("sceneimport::2.0")
        usdrender_node = self._find_first_node_by_type("usdrender_rop")
        param_changes = []
       
        # Set resolution based on global setting
        if self.resolution == "2k":
            resolution_x = 2048
            resolution_y = 1432
        else:  # 4k
            resolution_x = 4096
            resolution_y = 2864
       
        # Karma ROP
        if karma_node and karma_node.type().name() == "karmarenderproperties":
            node_name = karma_node.name()
            render_path = os.path.join(output_dir, shot_name, f"{shot_name}.{hip_name}.{node_name}.$F4.exr").replace("\\", "/")
            os.makedirs(os.path.dirname(render_path), exist_ok=True)
            if not dry_run:
                karma_node.parm("picture").set(render_path)
            param_changes.append([node_name, "picture", render_path])
            if not dry_run:
                karma_node.parm("res_mode").set("manual")
            param_changes.append([node_name, "res_mode", "manual"])
            if not dry_run:
                karma_node.parm("resolutionx").set(resolution_x)
                karma_node.parm("resolutiony").set(resolution_y)
            param_changes.append([node_name, "resolutionx", str(resolution_x)])
            param_changes.append([node_name, "resolutiony", str(resolution_y)])
       
        # Scene Import Cameras
        if sceneimport_node and sceneimport_node.type().name() == "sceneimport::2.0":
            node_name = sceneimport_node.name()
            camera_path = shot_data.get("Scene Camera Path", "") or shot_data.get("camera path", "")
            if not dry_run and camera_path:
                sceneimport_node.parm("objects").set(camera_path)
            param_changes.append([node_name, "objects", camera_path])
       
        # USD Render ROP
        if usdrender_node and usdrender_node.type().name() == "usdrender_rop":
            node_name = usdrender_node.name()
            frame_range = int(shot_data.get("frame range", 1))
            if not skip_frame_range:
                if single_frame is not None:
                    if not dry_run:
                        usdrender_node.parm("f1").set(single_frame)
                        usdrender_node.parm("f2").set(single_frame)
                        usdrender_node.parm("f3").set(1)
                    param_changes.append([node_name, "f1", str(single_frame)])
                    param_changes.append([node_name, "f2", str(single_frame)])
                    param_changes.append([node_name, "f3", "1"])
                else:
                    if not dry_run:
                        usdrender_node.parm("f1").set(1)
                        usdrender_node.parm("f2").set(frame_range)
                        usdrender_node.parm("f3").set(1)
                    param_changes.append([node_name, "f1", "1"])
                    param_changes.append([node_name, "f2", str(frame_range)])
                    param_changes.append([node_name, "f3", "1"])
       
        return param_changes
    
    def process_shots(self, single_frame=None, render_both=True, use_sequence_prefix=False):
        """Process shots with node-by-node execution and session-based retry mechanism"""
        self.log_area.clear()
        self.header_color_index = 0
        self.shot_times = []
        self.current_shot_params = {}
        csv_path = self.csv_path.text().strip()
        if not csv_path or not os.path.exists(csv_path):
            self.log_message("Error: Please select a valid CSV file.", "ERROR")
            return
        input_dir = os.path.dirname(csv_path)
        if os.path.basename(input_dir) != "INPUT data":
            self.log_message("Error: CSV file must be in an 'INPUT data' directory.", "ERROR")
            return
        base_folder = os.path.dirname(input_dir)
        if not os.path.exists(base_folder):
            self.log_message("Error: Derived base folder does not exist.", "ERROR")
            return
        parameters_dir = os.path.join(base_folder, "Parameters")
        output_dir = os.path.join(base_folder, "Output data")
        self.log_message(f"Using JSON parameters directory: {parameters_dir}", "INFO")
        self.log_message(f"Using output directory: {output_dir}", "INFO")
        self.log_message(f"Using input data directory: {input_dir}", "INFO")
        self.is_dry_run = self.dry_run_cb.isChecked()
        
        # Read CSV
        try:
            with open(csv_path, 'r', newline='', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                field_map = {h.lower(): h for h in reader.fieldnames or []}
                def get_val(row, key_like, default=""):
                    if key_like in row and row[key_like]:
                        return row[key_like]
                    lk = key_like.lower()
                    if lk in field_map:
                        return row.get(field_map[lk], default)
                    for k in row.keys():
                        if k.strip().lower() == lk:
                            return row.get(k, default)
                    return default
                shots = []
                for idx, row in enumerate(reader):
                    shot_name = get_val(row, "Shot names", f"shot_{idx}").strip()
                    fr_raw = get_val(row, "frame range", "1").strip()
                    cam_path = (get_val(row, "Scene Camera Path", "").strip() or
                                get_val(row, "camera path", "").strip())
                    try:
                        frame_range = int(fr_raw)
                    except Exception:
                        frame_range = 1
                    shots.append({
                        "Shot names": shot_name,
                        "frame range": frame_range,
                        "camera path": cam_path,
                        "Scene Camera Path": cam_path,
                    })
                self.log_message(f"Loaded CSV with {len(shots)} rows.", "INFO")
        except Exception as e:
            self.log_message(f"Error reading CSV: {str(e)}", "ERROR")
            return
        
        # Filter shots based on selection
        if self.selected_shot_names:
            filtered_shots = []
            for shot in shots:
                if shot.get("Shot names", "") in self.selected_shot_names:
                    filtered_shots.append(shot)
            shots = filtered_shots
            self.log_message(f"Using {len(shots)} selected shots for rendering", "INFO")
        else:
            self.log_message("No shots selected, using all shots from CSV", "WARNING")
        
        # Load progress if retry mechanism is enabled
        progress = self.load_progress()
        start_shot_index = 0
        start_frame = None
        start_engine = None
        
        if progress:
            # Display progress summary
            self.display_progress_summary(progress)
            
            self.last_render_mode = progress.get("mode")
            
            # Filter shots to start from the first non-completed shot
            filtered_shots = []
            for shot in shots:
                shot_name = shot["Shot names"]
                
                # Find the shot in progress data
                shot_progress = None
                for s in progress.get("shots", []):
                    if s.get("shot_name") == shot_name:
                        shot_progress = s
                        break
                
                # If shot is not in progress data or not completed, add it to filtered shots
                if not shot_progress or shot_progress.get("status") != "completed":
                    filtered_shots.append(shot)
                else:
                    self.log_message(f"Skipping completed shot: {shot_name}", "INFO")
            
            shots = filtered_shots
            self.log_message(f"Continuing with {len(shots)} remaining shots", "INFO")
        
        # Initialize progress data if it doesn't exist
        if not progress and self.retry_mechanism_cb.isChecked():
            mode = "auto-run-sequence" if self.is_auto_run_sequence else ("full" if single_frame is None else "single")
            progress = self.initialize_progress_data(mode, shots)
            
            # Save initial progress data
            progress_file = self.get_progress_file_path()
            try:
                with open(progress_file, 'w') as f:
                    json.dump(progress, f, indent=2)
            except Exception as e:
                self.log_message(f"Error saving initial progress: {str(e)}", "ERROR")
        
        # Generate parameters for both engines
        self.analyze_lop_structure(parameters_dir)  # For Karma
        self.generate_json_parameters(parameters_dir)  # For Mantra
        self.start_time = time.time()
        self.total_shots = len(shots)
        self.processed_shots = 0
        
        # Determine render mode text
        if self.is_auto_run_sequence:
            render_type = "AUTO-RUN SEQUENCE (skipping FML frames)"
        elif use_sequence_prefix:
            render_type = "SEQUENCE"
        else:
            render_type = "FULL"
            
        render_mode = "Single Frame" if single_frame is not None else "Full Range"
        mode_text = "DRY RUN (Settings Preview)" if self.is_dry_run else "RENDERING"
        resolution_text = f"Resolution: {self.resolution.upper()}"
        self.log_message(f"Processing {len(shots)} shots for BOTH KARMA AND MANTRA {render_type} RENDER ({render_mode}) - {mode_text} - {resolution_text}", "INFO")
        if single_frame is not None:
            self.log_message(f"Target frame: {single_frame}", "INFO")
        if self.is_dry_run:
            self.log_message("*** DRY RUN MODE - No actual rendering will occur ***", "INFO")
            self.log_message("The following settings would be applied:", "INFO")
        else:
            self.log_message(f"Starting actual Karma and Mantra rendering...", "INFO")
        
        # Initialize progress bars
        self.shot_progress_bar.setVisible(True)
        self.shot_progress_bar.setMaximum(len(shots))
        self.shot_progress_bar.setValue(0)
        self.shot_progress_bar.setFormat(f"Shot %v/%m (%p%)")
        
        self.frame_progress_bar.setVisible(True)
        self.frame_progress_bar.setMaximum(0)  # Indeterminate until we know frame count
        self.frame_progress_bar.setValue(0)
        self.frame_progress_bar.setFormat("Frame: Calculating...")
        
        # Store all changes for final summary
        all_shot_changes = []
        
        # Set initial frame once at the beginning (only if real render)
        if not self.is_dry_run:
            initial_frame = single_frame if single_frame is not None else 1
            try:
                hou.setFrame(float(initial_frame))
                self.log_message(f"Set Houdini current frame to: {initial_frame}", "INFO")
            except Exception as e:
                self.log_message(f"Error setting Houdini frame: {str(e)}", "ERROR")
        
        for shot_idx, shot in enumerate(shots):
            actual_shot_index = start_shot_index + shot_idx  # Calculate actual index in original list
            shot_name = shot["Shot names"]
            frame_range = max(int(shot["frame range"]), 1)
            
            # Update shot progress
            self.shot_progress_bar.setValue(shot_idx + 1)
            
            # Set frame progress max for this shot
            if single_frame is not None:
                self.frame_progress_bar.setMaximum(1)
            else:
                self.frame_progress_bar.setMaximum(frame_range)
            self.frame_progress_bar.setValue(0)
            self.frame_progress_bar.setFormat(f"Frame: %v/{frame_range if single_frame is None else 1} (%p%)")
            
            # Check if this shot has failed frames that need to be retried
            retry_frames = {}
            if progress:
                for shot_progress in progress.get("shots", []):
                    if shot_progress.get("shot_name") == shot_name:
                        for engine_name, engine_data in shot_progress.get("engines", {}).items():
                            failed_frames = engine_data.get("failed_frames", {})
                            if failed_frames:
                                retry_frames[engine_name] = list(failed_frames.keys())
                        break
            
            # Process both engines for each shot
            engines_to_process = ["Karma", "Mantra"]
            
            # If we have a saved engine, start from that one
            if start_engine and start_engine in engines_to_process:
                engine_idx = engines_to_process.index(start_engine)
                engines_to_process = engines_to_process[engine_idx:]
                start_engine = None  # Reset after first use
            
            for engine in engines_to_process:
                self.log_message(f"{'='*50}", "INFO")
                if self.is_auto_run_sequence:
                    self.log_message(f"PROCESSING {engine.upper()} for AUTO-RUN SEQUENCE shot {actual_shot_index + 1}/{start_shot_index + len(shots)}: {shot_name}", "INFO")
                elif use_sequence_prefix:
                    self.log_message(f"PROCESSING {engine.upper()} for SEQUENCE shot {actual_shot_index + 1}/{start_shot_index + len(shots)}: Sequence_{shot_name}", "INFO")
                else:
                    self.log_message(f"PROCESSING {engine.upper()} for shot {actual_shot_index + 1}/{start_shot_index + len(shots)}: {shot_name}", "INFO")
                self.log_message(f"{'='*50}", "INFO")
                
                shot_start_time = time.time()
                self.processed_shots = shot_idx + 1
                self.update_eta()
                QtWidgets.QApplication.processEvents()
                
                if engine == "Karma":
                    # Process Karma render
                    changes = self.apply_karma_parameters(shot, self.is_dry_run, single_frame, use_sequence_prefix)
                    
                    # Store changes for the final summary
                    display_shot_name = shot_name
                    if use_sequence_prefix and not self.is_auto_run_sequence:
                        display_shot_name = f"Sequence_{shot_name}"
                    for change in changes:
                        change_with_shot = [display_shot_name] + change
                        all_shot_changes.append(change_with_shot)
                    
                    # Execute actual render if not in dry run
                    if not self.is_dry_run:
                        usdrender_node = self._find_first_node_by_type("usdrender_rop")
                        if usdrender_node:
                            try:
                                self.log_message(f"[Karma] Starting render...", "RENDER")
                                render_start_time = time.time()
                                
                                if self.is_auto_run_sequence and single_frame is None:
                                    # Auto-run sequence mode: render frame-by-frame, skipping FML frames
                                    for frame in range(1, frame_range+1):
                                        # Check if this frame needs to be retried
                                        if engine in retry_frames and str(frame) in retry_frames[engine]:
                                            self.log_message(f"[Karma] Retrying failed frame {frame}", "INFO")
                                            
                                            # Set frame range for this frame
                                            usdrender_node.parm("f1").set(frame)
                                            usdrender_node.parm("f2").set(frame)
                                            usdrender_node.parm("f3").set(1)
                                            
                                            try:
                                                usdrender_node.render()
                                                # Mark frame as completed
                                                self.save_progress(shot_name, engine, frame, "usdrender_rop", "completed")
                                                self.log_message(f"[Karma] Frame {frame} retry completed successfully", "RENDER")
                                            except Exception as e:
                                                # Mark frame as failed again
                                                self.save_progress(shot_name, engine, frame, "usdrender_rop", "failed", str(e))
                                                self.log_message(f"[Karma] Frame {frame} retry failed: {str(e)}", "ERROR")
                                            continue
                                        
                                        if self.was_fml_rendered(shot_name, frame):
                                            self.log_message(f"[Karma] Skipping frame {frame} (already rendered in FML)", "INFO")
                                            # Update frame progress even for skipped frames
                                            self.frame_progress_bar.setValue(frame)
                                            continue
                                        
                                        # Normal rendering for new frames
                                        usdrender_node.parm("f1").set(frame)
                                        usdrender_node.parm("f2").set(frame)
                                        usdrender_node.parm("f3").set(1)
                                        usdrender_node.render()
                                        
                                        # Save progress after each frame
                                        self.save_progress(shot_name, engine, frame, "usdrender_rop", "completed")
                                        
                                        # Update frame progress
                                        self.frame_progress_bar.setValue(frame)
                                else:
                                    # Normal render mode
                                    if single_frame is not None:
                                        # Check if this frame needs to be retried
                                        if engine in retry_frames and str(single_frame) in retry_frames[engine]:
                                            self.log_message(f"[Karma] Retrying failed frame {single_frame}", "INFO")
                                            
                                            try:
                                                usdrender_node.render(frame_range=(single_frame, single_frame, 1))
                                                self.save_progress(shot_name, engine, single_frame, "usdrender_rop", "completed")
                                                self.log_message(f"[Karma] Frame {single_frame} retry completed successfully", "RENDER")
                                            except Exception as e:
                                                self.save_progress(shot_name, engine, single_frame, "usdrender_rop", "failed", str(e))
                                                self.log_message(f"[Karma] Frame {single_frame} retry failed: {str(e)}", "ERROR")
                                        else:
                                            usdrender_node.render(frame_range=(single_frame, single_frame, 1))
                                            self.save_progress(shot_name, engine, single_frame, "usdrender_rop", "completed")
                                    else:
                                        # Full range rendering
                                        usdrender_node.render()
                                        # Mark all frames as completed
                                        for frame in range(1, frame_range + 1):
                                            self.save_progress(shot_name, engine, frame, "usdrender_rop", "completed")
                                    
                                    # Update frame progress to complete
                                    self.frame_progress_bar.setValue(frame_range if single_frame is None else 1)
                                
                                render_time = time.time() - render_start_time
                                self.shot_times.append(render_time)
                                self.log_message(f"[Karma] Render completed successfully", "RENDER")
                            except Exception as e:
                                # Save error information
                                self.save_progress(shot_name, engine, single_frame if single_frame is not None else frame_range, "usdrender_rop", "failed", str(e))
                                self.log_message(f"[Karma] Render failed: {str(e)}", "ERROR")
                        else:
                            self.log_message("Error: No usdrender_rop node found to render with.", "ERROR")
                    else:
                        # In dry run mode, update frame progress to complete
                        self.frame_progress_bar.setValue(frame_range if single_frame is None else 1)
                else:
                    # Process Mantra render
                    out_context = hou.node("/out")
                    if not out_context:
                        self.log_message("Error: /out context not found.", "ERROR")
                        continue
                    merge_nodes = [node for node in out_context.allSubChildren() if node.type().name() == "merge"]
                    if not merge_nodes:
                        self.log_message("Error: No merge nodes found in /out.", "ERROR")
                        continue
                    
                    # Process each merge node
                    for merge_node in merge_nodes:
                        self.log_message(f"Processing merge node: {merge_node.path()}", "INFO")
                        
                        mantra_nodes = self.get_connected_nodes(merge_node, node_type="ifd")
                        if mantra_nodes and self.show_params_cb.isChecked():
                            self.log_message(f"Found {len(mantra_nodes)} mantra nodes for merge node {merge_node.path()}", "INFO")
                        
                        # Identify crowd node and other nodes
                        crowd_node = None
                        other_nodes = []
                        for node in mantra_nodes:
                            if "crowd" in node.name().lower():
                                crowd_node = node
                            else:
                                other_nodes.append(node)
                        
                        # Process crowd node first if it exists
                        if crowd_node:
                            node_name = crowd_node.name()
                            json_file_path = os.path.join(parameters_dir, f"{node_name}.json")
                            if os.path.exists(json_file_path):
                                self.log_message(f"[{node_name}] JSON file already exists, will overwrite", "INFO")
                            
                            params = self.load_json_parameters(json_file_path)
                            if params:
                                self.log_message(f"[{node_name}] Applying parameters for shot {shot_name}", "INFO")
                                
                                # Apply parameters and get changes
                                changes = self.apply_mantra_parameters(crowd_node, params, shot, self.is_dry_run, single_frame, output_dir, use_sequence_prefix)
                                
                                # Add node name to each change and collect
                                display_shot_name = shot_name
                                if use_sequence_prefix and not self.is_auto_run_sequence:
                                    display_shot_name = f"Sequence_{shot_name}"
                                for change in changes:
                                    change_with_node = [node_name] + change
                                    all_shot_changes.append([display_shot_name] + change_with_node)
                                
                                # Get resolution
                                if self.resolution == "2k":
                                    resolution_x = 2048
                                    resolution_y = 1432
                                else:  # 4k
                                    resolution_x = 4096
                                    resolution_y = 2864
                                
                                # Copy parameters to other nodes (without frame range)
                                self.copy_parameters_from_crowd(crowd_node, other_nodes, resolution_x, resolution_y, skip_frame_range=True)
                                
                                if not self.is_dry_run:
                                    try:
                                        self.log_message(f"[{node_name}] Starting render...", "RENDER")
                                        render_start_time = time.time()
                                        
                                        if self.is_auto_run_sequence and single_frame is None:
                                            # Auto-run sequence mode: render frame-by-frame, skipping FML frames
                                            for frame in range(1, frame_range+1):
                                                # Check if this frame needs to be retried
                                                if engine in retry_frames and str(frame) in retry_frames[engine]:
                                                    self.log_message(f"[{node_name}] Retrying failed frame {frame}", "INFO")
                                                    
                                                    crowd_node.parm("f1").set(frame)
                                                    crowd_node.parm("f2").set(frame)
                                                    crowd_node.parm("f3").set(1)
                                                    
                                                    try:
                                                        crowd_node.render()
                                                        self.save_progress(shot_name, engine, frame, node_name, "completed")
                                                        self.log_message(f"[{node_name}] Frame {frame} retry completed successfully", "RENDER")
                                                    except Exception as e:
                                                        self.save_progress(shot_name, engine, frame, node_name, "failed", str(e))
                                                        self.log_message(f"[{node_name}] Frame {frame} retry failed: {str(e)}", "ERROR")
                                                    continue
                                                
                                                if self.was_fml_rendered(shot_name, frame):
                                                    self.log_message(f"[{node_name}] Skipping frame {frame} (already rendered in FML)", "INFO")
                                                    # Update frame progress even for skipped frames
                                                    self.frame_progress_bar.setValue(frame)
                                                    continue
                                                
                                                # Normal rendering for new frames
                                                crowd_node.parm("f1").set(frame)
                                                crowd_node.parm("f2").set(frame)
                                                crowd_node.parm("f3").set(1)
                                                crowd_node.render()
                                                
                                                # Save progress after each frame
                                                self.save_progress(shot_name, engine, frame, node_name, "completed")
                                                
                                                # Update frame progress
                                                self.frame_progress_bar.setValue(frame)
                                        else:
                                            # Normal render mode
                                            if single_frame is not None:
                                                # Check if this frame needs to be retried
                                                if engine in retry_frames and str(single_frame) in retry_frames[engine]:
                                                    self.log_message(f"[{node_name}] Retrying failed frame {single_frame}", "INFO")
                                                    
                                                    try:
                                                        crowd_node.render()
                                                        self.save_progress(shot_name, engine, single_frame, node_name, "completed")
                                                        self.log_message(f"[{node_name}] Frame {single_frame} retry completed successfully", "RENDER")
                                                    except Exception as e:
                                                        self.save_progress(shot_name, engine, single_frame, node_name, "failed", str(e))
                                                        self.log_message(f"[{node_name}] Frame {single_frame} retry failed: {str(e)}", "ERROR")
                                                else:
                                                    crowd_node.render()
                                                    self.save_progress(shot_name, engine, single_frame, node_name, "completed")
                                            else:
                                                # Full range rendering
                                                crowd_node.render()
                                                # Mark all frames as completed
                                                for frame in range(1, frame_range + 1):
                                                    self.save_progress(shot_name, engine, frame, node_name, "completed")
                                            
                                            # Update frame progress to complete
                                            self.frame_progress_bar.setValue(frame_range if single_frame is None else 1)
                                        
                                        render_time = time.time() - render_start_time
                                        self.shot_times.append(render_time)
                                        self.log_message(f"[{node_name}] Render completed successfully", "RENDER")
                                    except Exception as e:
                                        # Save error information with node name
                                        self.save_progress(shot_name, engine, single_frame if single_frame is not None else frame_range, node_name, "failed", str(e))
                                        self.log_message(f"[{node_name}] Render failed: {str(e)}", "ERROR")
                                else:
                                    # In dry run mode, update frame progress to complete
                                    self.frame_progress_bar.setValue(frame_range if single_frame is None else 1)
                            
                            # Process other nodes
                            for node in other_nodes:
                                node_name = node.name()
                                json_file_path = os.path.join(parameters_dir, f"{node_name}.json")
                                if os.path.exists(json_file_path):
                                    self.log_message(f"[{node_name}] JSON file already exists, will overwrite", "INFO")
                                
                                params = self.load_json_parameters(json_file_path)
                                if not params:
                                    self.log_message(f"[{node_name}] No parameters loaded, skipping", "WARNING")
                                    continue
                                
                                self.log_message(f"[{node_name}] Applying parameters for shot {shot_name}", "INFO")
                                
                                # Apply parameters and get changes
                                changes = self.apply_mantra_parameters(node, params, shot, self.is_dry_run, single_frame, output_dir, use_sequence_prefix)
                                
                                # Add node name to each change and collect
                                display_shot_name = shot_name
                                if use_sequence_prefix and not self.is_auto_run_sequence:
                                    display_shot_name = f"Sequence_{shot_name}"
                                for change in changes:
                                    change_with_node = [node_name] + change
                                    all_shot_changes.append([display_shot_name] + change_with_node)
                                
                                if not self.is_dry_run:
                                    try:
                                        self.log_message(f"[{node_name}] Starting render...", "RENDER")
                                        render_start_time = time.time()
                                        
                                        if self.is_auto_run_sequence and single_frame is None:
                                            # Auto-run sequence mode: render frame-by-frame, skipping FML frames
                                            for frame in range(1, frame_range+1):
                                                # Check if this frame needs to be retried
                                                if engine in retry_frames and str(frame) in retry_frames[engine]:
                                                    self.log_message(f"[{node_name}] Retrying failed frame {frame}", "INFO")
                                                    
                                                    node.parm("f1").set(frame)
                                                    node.parm("f2").set(frame)
                                                    node.parm("f3").set(1)
                                                    
                                                    try:
                                                        node.render()
                                                        self.save_progress(shot_name, engine, frame, node_name, "completed")
                                                        self.log_message(f"[{node_name}] Frame {frame} retry completed successfully", "RENDER")
                                                    except Exception as e:
                                                        self.save_progress(shot_name, engine, frame, node_name, "failed", str(e))
                                                        self.log_message(f"[{node_name}] Frame {frame} retry failed: {str(e)}", "ERROR")
                                                    continue
                                                
                                                if self.was_fml_rendered(shot_name, frame):
                                                    self.log_message(f"[{node_name}] Skipping frame {frame} (already rendered in FML)", "INFO")
                                                    # Update frame progress even for skipped frames
                                                    self.frame_progress_bar.setValue(frame)
                                                    continue
                                                
                                                # Normal rendering for new frames
                                                node.parm("f1").set(frame)
                                                node.parm("f2").set(frame)
                                                node.parm("f3").set(1)
                                                node.render()
                                                
                                                # Save progress after each frame
                                                self.save_progress(shot_name, engine, frame, node_name, "completed")
                                                
                                                # Update frame progress
                                                self.frame_progress_bar.setValue(frame)
                                        else:
                                            # Normal render mode
                                            if single_frame is not None:
                                                # Check if this frame needs to be retried
                                                if engine in retry_frames and str(single_frame) in retry_frames[engine]:
                                                    self.log_message(f"[{node_name}] Retrying failed frame {single_frame}", "INFO")
                                                    
                                                    try:
                                                        node.render()
                                                        self.save_progress(shot_name, engine, single_frame, node_name, "completed")
                                                        self.log_message(f"[{node_name}] Frame {single_frame} retry completed successfully", "RENDER")
                                                    except Exception as e:
                                                        self.save_progress(shot_name, engine, single_frame, node_name, "failed", str(e))
                                                        self.log_message(f"[{node_name}] Frame {single_frame} retry failed: {str(e)}", "ERROR")
                                                else:
                                                    node.render()
                                                    self.save_progress(shot_name, engine, single_frame, node_name, "completed")
                                            else:
                                                # Full range rendering
                                                node.render()
                                                # Mark all frames as completed
                                                for frame in range(1, frame_range + 1):
                                                    self.save_progress(shot_name, engine, frame, node_name, "completed")
                                            
                                            # Update frame progress to complete
                                            self.frame_progress_bar.setValue(frame_range if single_frame is None else 1)
                                        
                                        render_time = time.time() - render_start_time
                                        self.shot_times.append(render_time)
                                        self.log_message(f"[{node_name}] Render completed successfully", "RENDER")
                                    except Exception as e:
                                        # Save error information with node name
                                        self.save_progress(shot_name, engine, single_frame if single_frame is not None else frame_range, node_name, "failed", str(e))
                                        self.log_message(f"[{node_name}] Render failed: {str(e)}", "ERROR")
                                else:
                                    # In dry run mode, update frame progress to complete
                                    self.frame_progress_bar.setValue(frame_range if single_frame is None else 1)
                            
                            if self.show_params_cb.isChecked():
                                display_shot_name = shot_name
                                if use_sequence_prefix and not self.is_auto_run_sequence:
                                    display_shot_name = f"Sequence_{shot_name}"
                                self.display_shot_parameters(display_shot_name)
                    
                    # Track time per shot (for ETA when actually rendering)
                    if not self.is_dry_run:
                        self.shot_times.append(time.time() - shot_start_time)
        
        # Show final summary table for both Karma and Mantra
        if self.is_dry_run and self.show_params_cb.isChecked() and all_shot_changes:
            self.log_message("Final Parameter Summary Table:", "INFO")
            headers = ["Shot Name", "Node", "Parameter", "Value"]
            self.log_table(headers, all_shot_changes, "Complete Parameter Changes Summary")
        total_time = time.time() - self.start_time if self.start_time else 0
        total_minutes = int(total_time // 60)
        total_seconds = int(total_time % 60)
        
        # Hide progress bars when done
        self.shot_progress_bar.setVisible(False)
        self.frame_progress_bar.setVisible(False)
        
        self.log_message(f"{'='*50}", "INFO")
        
        if self.is_auto_run_sequence:
            final_msg = "AUTO-RUN SEQUENCE RENDER DRY RUN COMPLETED" if self.is_dry_run else "AUTO-RUN SEQUENCE RENDERING COMPLETED"
        elif use_sequence_prefix:
            final_msg = f"BOTH KARMA AND MANTRA SEQUENCE RENDER DRY RUN COMPLETED" if self.is_dry_run else f"BOTH KARMA AND MANTRA SEQUENCE RENDERING COMPLETED"
        else:
            final_msg = f"BOTH KARMA AND MANTRA FULL RENDER DRY RUN COMPLETED" if self.is_dry_run else f"BOTH KARMA AND MANTRA FULL RENDERING COMPLETED"
                
        render_mode = "Single Frame" if single_frame is not None else "Full Range"
        self.log_message(f"{final_msg}! ({render_mode})", "INFO")
        self.log_message(f"Total Time: {total_minutes}m {total_seconds}s", "INFO")
        self.log_message(f"{'='*50}", "INFO")
        
        # Reset progress file when rendering completes
        if self.retry_mechanism_cb.isChecked():
            self.reset_progress()
    
    def process_fml_shots(self):
        """Process shots for FML (First, Middle, Last) rendering with session-based retry mechanism"""
        self.log_area.clear()
        self.header_color_index = 0
        self.shot_times = []
        self.current_shot_params = {}
        self.fml_rendered_frames = {}  # Reset FML frame tracking
        
        csv_path = self.csv_path.text().strip()
        if not csv_path or not os.path.exists(csv_path):
            self.log_message("Error: Please select a valid CSV file.", "ERROR")
            return
            
        input_dir = os.path.dirname(csv_path)
        if os.path.basename(input_dir) != "INPUT data":
            self.log_message("Error: CSV file must be in an 'INPUT data' directory.", "ERROR")
            return
            
        base_folder = os.path.dirname(input_dir)
        if not os.path.exists(base_folder):
            self.log_message("Error: Derived base folder does not exist.", "ERROR")
            return
            
        parameters_dir = os.path.join(base_folder, "Parameters")
        output_dir = os.path.join(base_folder, "Output data")
        
        self.log_message(f"Using JSON parameters directory: {parameters_dir}", "INFO")
        self.log_message(f"Using output directory: {output_dir}", "INFO")
        self.log_message(f"Using input data directory: {input_dir}", "INFO")
        
        self.is_dry_run = self.dry_run_cb.isChecked()
        
        # Read CSV
        try:
            with open(csv_path, 'r', newline='', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                field_map = {h.lower(): h for h in reader.fieldnames or []}
                
                def get_val(row, key_like, default=""):
                    if key_like in row and row[key_like]:
                        return row[key_like]
                    lk = key_like.lower()
                    if lk in field_map:
                        return row.get(field_map[lk], default)
                    for k in row.keys():
                        if k.strip().lower() == lk:
                            return row.get(k, default)
                    return default
                
                shots = []
                for idx, row in enumerate(reader):
                    shot_name = get_val(row, "Shot names", f"shot_{idx}").strip()
                    fr_raw = get_val(row, "frame range", "1").strip()
                    cam_path = (get_val(row, "Scene Camera Path", "").strip() or
                                get_val(row, "camera path", "").strip())
                    try:
                        frame_range = int(fr_raw)
                    except Exception:
                        frame_range = 1
                    shots.append({
                        "Shot names": shot_name,
                        "frame range": frame_range,
                        "camera path": cam_path,
                        "Scene Camera Path": cam_path,
                    })
                self.log_message(f"Loaded CSV with {len(shots)} rows.", "INFO")
        except Exception as e:
            self.log_message(f"Error reading CSV: {str(e)}", "ERROR")
            return
        
        # Filter shots based on selection
        if self.selected_shot_names:
            filtered_shots = []
            for shot in shots:
                if shot.get("Shot names", "") in self.selected_shot_names:
                    filtered_shots.append(shot)
            shots = filtered_shots
            self.log_message(f"Using {len(shots)} selected shots for rendering", "INFO")
        else:
            self.log_message("No shots selected, using all shots from CSV", "WARNING")
        
        # Load progress if retry mechanism is enabled
        progress = self.load_progress()
        start_shot_index = 0
        start_frame = None
        start_frame_index = 0
        start_engine = None
        
        if progress:
            # Display progress summary
            self.display_progress_summary(progress)
            
            self.last_render_mode = progress.get("mode")
            
            # Filter shots to start from the first non-completed shot
            filtered_shots = []
            for shot in shots:
                shot_name = shot["Shot names"]
                
                # Find the shot in progress data
                shot_progress = None
                for s in progress.get("shots", []):
                    if s.get("shot_name") == shot_name:
                        shot_progress = s
                        break
                
                # If shot is not in progress data or not completed, add it to filtered shots
                if not shot_progress or shot_progress.get("status") != "completed":
                    filtered_shots.append(shot)
                else:
                    self.log_message(f"Skipping completed shot: {shot_name}", "INFO")
            
            shots = filtered_shots
            self.log_message(f"Continuing FML with {len(shots)} remaining shots", "INFO")
        
        # Initialize progress data if it doesn't exist
        if not progress and self.retry_mechanism_cb.isChecked():
            progress = self.initialize_progress_data("fml", shots)
            
            # Save initial progress data
            progress_file = self.get_progress_file_path()
            try:
                with open(progress_file, 'w') as f:
                    json.dump(progress, f, indent=2)
            except Exception as e:
                self.log_message(f"Error saving initial progress: {str(e)}", "ERROR")
        
        # Generate parameters for both engines
        self.analyze_lop_structure(parameters_dir)  # For Karma
        self.generate_json_parameters(parameters_dir)  # For Mantra
        
        self.start_time = time.time()
        self.total_shots = len(shots) * 2  # 2 engines (Karma and Mantra)
        self.processed_shots = 0
        
        mode_text = "DRY RUN (Settings Preview)" if self.is_dry_run else "RENDERING"
        resolution_text = f"Resolution: {self.resolution.upper()}"
        self.log_message(f"Processing {len(shots)} shots for FML (First, Middle, Last) frames - BOTH KARMA AND MANTRA - {mode_text} - {resolution_text}", "INFO")
        
        if self.is_dry_run:
            self.log_message("*** DRY RUN MODE - No actual rendering will occur ***", "INFO")
            self.log_message("The following settings would be applied:", "INFO")
        else:
            self.log_message(f"Starting actual FML rendering...", "INFO")
        
        # Initialize progress bars
        self.shot_progress_bar.setVisible(True)
        self.shot_progress_bar.setMaximum(len(shots))
        self.shot_progress_bar.setValue(0)
        self.shot_progress_bar.setFormat(f"Shot %v/%m (%p%)")
        
        self.frame_progress_bar.setVisible(True)
        self.frame_progress_bar.setMaximum(3)  # Always 3 FML frames per shot
        self.frame_progress_bar.setValue(0)
        self.frame_progress_bar.setFormat(f"Frame: %v/3 (%p%)")
        
        # Store all changes for final summary table
        all_shot_changes = []
        
        # Set initial frame once at the beginning (only if real render)
        if not self.is_dry_run:
            try:
                hou.setFrame(1)
                self.log_message("Set Houdini current frame to: 1", "INFO")
            except Exception as e:
                self.log_message(f"Error setting Houdini frame: {str(e)}", "ERROR")
        
        # Process each shot
        for shot_idx, shot in enumerate(shots):
            actual_shot_index = start_shot_index + shot_idx  # Calculate actual index in original list
            shot_name = shot["Shot names"]
            frame_range = max(int(shot["frame range"]), 1)
            
            # Calculate FML frames
            first_frame = 1
            middle_frame = (frame_range + 1) // 2  # Integer division
            last_frame = frame_range
            
            fml_frames = [
                ("First", first_frame),
                ("Middle", middle_frame),
                ("Last", last_frame)
            ]
            
            # Update shot progress
            self.shot_progress_bar.setValue(shot_idx + 1)
            
            # Reset frame progress for new shot
            self.frame_progress_bar.setValue(0)
            
            # Check if this shot has failed frames that need to be retried
            retry_frames = {}
            if progress:
                for shot_progress in progress.get("shots", []):
                    if shot_progress.get("shot_name") == shot_name:
                        for engine_name, engine_data in shot_progress.get("engines", {}).items():
                            failed_frames = engine_data.get("failed_frames", {})
                            if failed_frames:
                                retry_frames[engine_name] = list(failed_frames.keys())
                        break
            
            # If we have a saved frame, start from that one
            if start_frame:
                # Find the index of the saved frame
                for i, (label, frame_num) in enumerate(fml_frames):
                    if frame_num == start_frame:
                        start_frame_index = i
                        break
                start_frame = None  # Reset after first use
            
            # Process both engines for each shot
            engines_to_process = ["Karma", "Mantra"]
            
            # If we have a saved engine, start from that one
            if start_engine and start_engine in engines_to_process:
                engine_idx = engines_to_process.index(start_engine)
                engines_to_process = engines_to_process[engine_idx:]
                start_engine = None  # Reset after first use
            
            for engine in engines_to_process:
                self.processed_shots += 1
                self.update_eta()
                QtWidgets.QApplication.processEvents()
                
                self.log_message(f"{'='*50}", "INFO")
                self.log_message(f"PROCESSING {engine.upper()} for shot {actual_shot_index + 1}/{start_shot_index + len(shots)}: {shot_name} | FML frames", "INFO")
                self.log_message(f"{'='*50}", "INFO")
                
                shot_start_time = time.time()
                
                if engine == "Karma":
                    # Process Karma render for FML frames
                    # Apply parameters without setting frame range
                    changes = self.apply_karma_parameters(shot, self.is_dry_run, skip_frame_range=True)
                    
                    # Store changes for the final summary table
                    for change in changes:
                        # Format: [Shot Name, Frame Label (Frame Num), Node, Parameter, New Value]
                        change_with_shot = [shot_name, "FML"] + change
                        all_shot_changes.append(change_with_shot)
                    
                    # Execute actual render if not in dry run
                    if not self.is_dry_run:
                        usdrender_node = self._find_first_node_by_type("usdrender_rop")
                        if usdrender_node:
                            try:
                                self.log_message(f"[Karma] Starting FML render...", "RENDER")
                                render_start_time = time.time()
                                
                                # Render each FML frame separately
                                for frame_idx in range(start_frame_index, len(fml_frames)):
                                    frame_label, frame_num = fml_frames[frame_idx]
                                    
                                    # Check if this frame needs to be retried
                                    if engine in retry_frames and str(frame_num) in retry_frames[engine]:
                                        self.log_message(f"[Karma] Retrying failed {frame_label} frame {frame_num}", "INFO")
                                        
                                        # Set frame range for this frame
                                        usdrender_node.parm("f1").set(frame_num)
                                        usdrender_node.parm("f2").set(frame_num)
                                        usdrender_node.parm("f3").set(1)
                                        
                                        try:
                                            usdrender_node.render()
                                            # Track that this FML frame was rendered
                                            self.track_fml_render(shot_name, frame_num)
                                            # Mark frame as completed
                                            self.save_progress(shot_name, engine, frame_num, "usdrender_rop", "completed")
                                            # Update frame progress
                                            self.frame_progress_bar.setValue(frame_idx + 1)
                                            self.log_message(f"[Karma] {frame_label} frame {frame_num} retry completed successfully", "RENDER")
                                        except Exception as e:
                                            # Mark frame as failed again
                                            self.save_progress(shot_name, engine, frame_num, "usdrender_rop", "failed", str(e))
                                            self.log_message(f"[Karma] {frame_label} frame {frame_num} retry failed: {str(e)}", "ERROR")
                                        continue
                                    
                                    # Set frame range for this frame
                                    usdrender_node.parm("f1").set(frame_num)
                                    usdrender_node.parm("f2").set(frame_num)
                                    usdrender_node.parm("f3").set(1)
                                    
                                    # Render this frame
                                    usdrender_node.render()
                                    
                                    # Track that this FML frame was rendered
                                    self.track_fml_render(shot_name, frame_num)
                                    
                                    # Update frame progress
                                    self.frame_progress_bar.setValue(frame_idx + 1)
                                    
                                    # Save progress after each frame
                                    self.save_progress(shot_name, engine, frame_num, "usdrender_rop", "completed")
                                    
                                    self.log_message(f"[Karma] {frame_label} frame {frame_num} render completed", "RENDER")
                                
                                render_time = time.time() - render_start_time
                                self.shot_times.append(render_time)
                                self.log_message(f"[Karma] FML render completed successfully", "RENDER")
                            except Exception as e:
                                # Save error information
                                self.save_progress(shot_name, engine, frame_num, "usdrender_rop", "failed", str(e))
                                self.log_message(f"[Karma] FML render failed: {str(e)}", "ERROR")
                        else:
                            self.log_message("Error: No usdrender_rop node found to render with.", "ERROR")
                    else:
                        # In dry run mode, update frame progress to complete
                        self.frame_progress_bar.setValue(3)
                else:
                    # Process Mantra render for FML frames
                    out_context = hou.node("/out")
                    if not out_context:
                        self.log_message("Error: /out context not found.", "ERROR")
                        continue
                            
                    merge_nodes = [node for node in out_context.allSubChildren() if node.type().name() == "merge"]
                    if not merge_nodes:
                        self.log_message("Error: No merge nodes found in /out.", "ERROR")
                        continue
                    
                    # Process each merge node
                    for merge_node in merge_nodes:
                        self.log_message(f"Processing merge node: {merge_node.path()}", "INFO")
                        
                        mantra_nodes = self.get_connected_nodes(merge_node, node_type="ifd")
                        if mantra_nodes and self.show_params_cb.isChecked():
                            self.log_message(f"Found {len(mantra_nodes)} mantra nodes for merge node {merge_node.path()}", "INFO")
                        
                        # Identify crowd node and other nodes
                        crowd_node = None
                        other_nodes = []
                        for node in mantra_nodes:
                            if "crowd" in node.name().lower():
                                crowd_node = node
                            else:
                                other_nodes.append(node)
                        
                        # Process crowd node first if it exists
                        if crowd_node:
                            node_name = crowd_node.name()
                            json_file_path = os.path.join(parameters_dir, f"{node_name}.json")
                            if os.path.exists(json_file_path):
                                self.log_message(f"[{node_name}] JSON file already exists, will overwrite", "INFO")
                            
                            params = self.load_json_parameters(json_file_path)
                            if params:
                                self.log_message(f"[{node_name}] Applying common parameters for shot {shot_name}", "INFO")
                                
                                # Apply common parameters and get changes
                                changes = self.apply_mantra_parameters_common(crowd_node, params, shot, self.is_dry_run, output_dir)
                                
                                # Add node name and frame info to each change and collect
                                for change in changes:
                                    change_with_node = [node_name] + change
                                    all_shot_changes.append([shot_name, "FML"] + change_with_node)
                                
                                # Get resolution
                                if self.resolution == "2k":
                                    resolution_x = 2048
                                    resolution_y = 1432
                                else:  # 4k
                                    resolution_x = 4096
                                    resolution_y = 2864
                                
                                # Copy common parameters to other nodes (without frame range)
                                self.copy_parameters_from_crowd(crowd_node, other_nodes, resolution_x, resolution_y, skip_frame_range=True)
                                
                                # Now, for each FML frame, set the frame and render
                                for frame_idx in range(start_frame_index, len(fml_frames)):
                                    frame_label, frame_num = fml_frames[frame_idx]
                                    
                                    # Check if this frame needs to be retried
                                    if engine in retry_frames and str(frame_num) in retry_frames[engine]:
                                        self.log_message(f"[{node_name}] Retrying failed {frame_label} frame {frame_num}", "INFO")
                                        
                                        # Set frame parameters for this frame
                                        crowd_node.parm("f1").set(frame_num)
                                        crowd_node.parm("f2").set(frame_num)
                                        crowd_node.parm("f3").set(1)
                                        
                                        try:
                                            crowd_node.render()
                                            render_time = time.time() - render_start_time
                                            self.shot_times.append(render_time)
                                            
                                            # Track that this FML frame was rendered
                                            self.track_fml_render(shot_name, frame_num)
                                            
                                            # Update frame progress
                                            self.frame_progress_bar.setValue(frame_idx + 1)
                                            
                                            # Save progress after each frame
                                            self.save_progress(shot_name, engine, frame_num, node_name, "completed")
                                            
                                            self.log_message(f"[{node_name}] {frame_label} frame {frame_num} retry completed successfully", "RENDER")
                                        except Exception as e:
                                            # Mark frame as failed again
                                            self.save_progress(shot_name, engine, frame_num, node_name, "failed", str(e))
                                            self.log_message(f"[{node_name}] {frame_label} frame {frame_num} retry failed: {str(e)}", "ERROR")
                                        continue
                                    
                                    # Set frame parameters for this frame
                                    crowd_node.parm("f1").set(frame_num)
                                    crowd_node.parm("f2").set(frame_num)
                                    crowd_node.parm("f3").set(1)
                                    
                                    if not self.is_dry_run:
                                        try:
                                            self.log_message(f"[{node_name}] Starting render for {frame_label} frame {frame_num}...", "RENDER")
                                            render_start_time = time.time()
                                            crowd_node.render()
                                            render_time = time.time() - render_start_time
                                            self.shot_times.append(render_time)
                                            
                                            # Track that this FML frame was rendered
                                            self.track_fml_render(shot_name, frame_num)
                                            
                                            # Update frame progress
                                            self.frame_progress_bar.setValue(frame_idx + 1)
                                            
                                            # Save progress after each frame
                                            self.save_progress(shot_name, engine, frame_num, node_name, "completed")
                                            
                                            self.log_message(f"[{node_name}] {frame_label} frame {frame_num} render completed successfully", "RENDER")
                                        except Exception as e:
                                            # Save error information with node name
                                            self.save_progress(shot_name, engine, frame_num, node_name, "failed", str(e))
                                            self.log_message(f"[{node_name}] {frame_label} frame {frame_num} render failed: {str(e)}", "ERROR")
                                    else:
                                        # In dry run mode, update frame progress
                                        self.frame_progress_bar.setValue(frame_idx + 1)
                            
                            # Process other nodes
                            for node in other_nodes:
                                node_name = node.name()
                                json_file_path = os.path.join(parameters_dir, f"{node_name}.json")
                                if os.path.exists(json_file_path):
                                    self.log_message(f"[{node_name}] JSON file already exists, will overwrite", "INFO")
                                
                                params = self.load_json_parameters(json_file_path)
                                if not params:
                                    self.log_message(f"[{node_name}] No parameters loaded, skipping", "WARNING")
                                    continue
                                
                                self.log_message(f"[{node_name}] Applying common parameters for shot {shot_name}", "INFO")
                                
                                # Apply common parameters and get changes
                                changes = self.apply_mantra_parameters_common(node, params, shot, self.is_dry_run, output_dir)
                                
                                # Add node name and frame info to each change and collect
                                for change in changes:
                                    change_with_node = [node_name] + change
                                    all_shot_changes.append([shot_name, "FML"] + change_with_node)
                                
                                # Now, for each FML frame, set the frame and render
                                for frame_idx in range(start_frame_index, len(fml_frames)):
                                    frame_label, frame_num = fml_frames[frame_idx]
                                    
                                    # Check if this frame needs to be retried
                                    if engine in retry_frames and str(frame_num) in retry_frames[engine]:
                                        self.log_message(f"[{node_name}] Retrying failed {frame_label} frame {frame_num}", "INFO")
                                        
                                        # Set frame parameters for this frame
                                        node.parm("f1").set(frame_num)
                                        node.parm("f2").set(frame_num)
                                        node.parm("f3").set(1)
                                        
                                        try:
                                            node.render()
                                            render_time = time.time() - render_start_time
                                            self.shot_times.append(render_time)
                                            
                                            # Track that this FML frame was rendered
                                            self.track_fml_render(shot_name, frame_num)
                                            
                                            # Update frame progress
                                            self.frame_progress_bar.setValue(frame_idx + 1)
                                            
                                            # Save progress after each frame
                                            self.save_progress(shot_name, engine, frame_num, node_name, "completed")
                                            
                                            self.log_message(f"[{node_name}] {frame_label} frame {frame_num} retry completed successfully", "RENDER")
                                        except Exception as e:
                                            # Mark frame as failed again
                                            self.save_progress(shot_name, engine, frame_num, node_name, "failed", str(e))
                                            self.log_message(f"[{node_name}] {frame_label} frame {frame_num} retry failed: {str(e)}", "ERROR")
                                        continue
                                    
                                    # Set frame parameters for this frame
                                    node.parm("f1").set(frame_num)
                                    node.parm("f2").set(frame_num)
                                    node.parm("f3").set(1)
                                    
                                    if not self.is_dry_run:
                                        try:
                                            self.log_message(f"[{node_name}] Starting render for {frame_label} frame {frame_num}...", "RENDER")
                                            render_start_time = time.time()
                                            node.render()
                                            render_time = time.time() - render_start_time
                                            self.shot_times.append(render_time)
                                            
                                            # Track that this FML frame was rendered
                                            self.track_fml_render(shot_name, frame_num)
                                            
                                            # Update frame progress
                                            self.frame_progress_bar.setValue(frame_idx + 1)
                                            
                                            # Save progress after each frame
                                            self.save_progress(shot_name, engine, frame_num, node_name, "completed")
                                            
                                            self.log_message(f"[{node_name}] {frame_label} frame {frame_num} render completed successfully", "RENDER")
                                        except Exception as e:
                                            # Save error information with node name
                                            self.save_progress(shot_name, engine, frame_num, node_name, "failed", str(e))
                                            self.log_message(f"[{node_name}] {frame_label} frame {frame_num} render failed: {str(e)}", "ERROR")
                                    else:
                                        # In dry run mode, update frame progress
                                        self.frame_progress_bar.setValue(frame_idx + 1)
                        
                        # Reset start_frame_index for next engine
                        start_frame_index = 0
                    
                    # Track time per shot (for ETA when actually rendering)
                    if not self.is_dry_run:
                        self.shot_times.append(time.time() - shot_start_time)
        
        # Show final summary table for FML if in dry run mode and show parameters is checked
        if self.is_dry_run and self.show_params_cb.isChecked() and all_shot_changes:
            self.log_message("FML Parameter Summary Table:", "INFO")
            headers = ["Shot Name", "Frame", "Node", "Parameter", "New Value"]
            self.log_table(headers, all_shot_changes, "FML Parameter Changes Summary")
            
        total_time = time.time() - self.start_time if self.start_time else 0
        total_minutes = int(total_time // 60)
        total_seconds = int(total_time % 60)
        
        # Hide progress bars when done
        self.shot_progress_bar.setVisible(False)
        self.frame_progress_bar.setVisible(False)
        
        self.log_message(f"{'='*50}", "INFO")
        final_msg = "FML RENDER DRY RUN COMPLETED" if self.is_dry_run else "FML RENDERING COMPLETED"
        self.log_message(f"{final_msg}!", "INFO")
        self.log_message(f"Total Time: {total_minutes}m {total_seconds}s", "INFO")
        self.log_message(f"{'='*50}", "INFO")
        
        # Set FML completion flag
        self.fml_completed = True
        
        # Reset progress file when rendering completes
        if self.retry_mechanism_cb.isChecked():
            self.reset_progress()
        
        # Auto-start sequence render if checkbox is checked and not in dry run mode
        if self.sequence_after_fml_cb.isChecked() and not self.is_dry_run:
            self.log_message("Auto-starting Sequence render after FML completion...", "INFO")
            self.log_message(f"This will use the same resolution as FML: {self.resolution.upper()}", "INFO")
            # Use a timer to ensure UI updates before starting the next render
            QtCore.QTimer.singleShot(1000, lambda: self.process_shots_auto_run())
            
    def process_shots_auto_run(self):
        """Process shots in auto-run mode after FML completion"""
        self.is_auto_run_sequence = True
        self.process_shots(single_frame=None, render_both=True, use_sequence_prefix=False)
        self.is_auto_run_sequence = False

def run_tool():
    dialog = UniversalRenderToolUI(hou.qt.mainWindow())
    dialog.show()
   
if __name__ == "__main__":
    run_tool()
   
run_tool()
